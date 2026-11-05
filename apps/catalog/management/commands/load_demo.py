"""Carrega dados de demonstração marcados "(exemplo)" (CA18).

Só roda com `DEMO_DATA=true`; sem a variável, recusa e sai com código ≠ 0.
Idempotente: rodar de novo atualiza os mesmos registros (e renova as datas, para
a confirmação do dia valer "hoje"). Mexe apenas em contas `@exemplo.invalid`.
Os vendedores não têm número de WhatsApp nem senha utilizável, e os anúncios
ficam sem foto (aparece o placeholder). Cobre todos os tipos e estados.

`load_demo --remove` apaga as contas de exemplo (`@exemplo.invalid` com perfil
de demonstração), os anúncios delas e os arquivos das fotos. Roda mesmo sem
`DEMO_DATA`: é o caminho para limpar uma instalação que publicou a demonstração.
Com `DEMO_DATA` desligado, a demonstração já não aparece ao público.
"""

from dataclasses import dataclass, field
from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.catalog.models import Category, Offer, OfferVariant, Seller
from apps.core import clock
from apps.core.text import unique_slug

DEMO_DOMAIN = "exemplo.invalid"


@dataclass
class DemoOffer:
    title: str
    category: str  # slug
    kind: str
    price_cents: int
    description: str = ""
    fulfillment: str = "Retirada no campus"
    status: str = Offer.Status.ACTIVE
    approval: str = Offer.Approval.APPROVED
    variants: list[tuple[str, int]] = field(default_factory=list)
    portion: str = ""
    ingredients: str = ""
    allergens: str = ""
    confirmed_today: bool = False
    closing_time: time | None = None
    confirmed_days_ago: int = 0  # idade de `last_confirmed_at` (venda pontual)
    hidden: bool = False


@dataclass
class DemoSeller:
    key: str
    name: str
    bio: str
    area: str
    hours: str
    trusted: bool
    offers: list[DemoOffer]


R = Offer.Kind.RECURRING
D = Offer.Kind.DAILY
O = Offer.Kind.ONE_OFF  # noqa: E741
S = Offer.Status

SELLERS = [
    DemoSeller(
        key="ana",
        name="Doces da Ana (exemplo)",
        bio="Doces caseiros feitos na véspera. Exemplo de vendedor fictício.",
        area="Bloco 3 e biblioteca",
        hours="Seg a sex, 10h às 17h",
        trusted=True,
        offers=[
            DemoOffer(
                "Cookies caseiros (exemplo)",
                "comidas-e-doces",
                R,
                600,
                "Cookies macios, feitos por encomenda ou com estoque do dia.",
                "Retirada no bloco 3, às 10h",
                variants=[("Tradicional", 600), ("Chocolate", 700), ("Red velvet", 800)],
                portion="1 cookie de 80 g",
                ingredients="Farinha de trigo, manteiga, açúcar, ovos, gotas de chocolate",
                allergens="Contém glúten, leite e ovos",
                confirmed_today=True,
            ),
            DemoOffer(
                "Brownie de chocolate (exemplo)",
                "comidas-e-doces",
                R,
                800,
                "Brownie úmido com cobertura de brigadeiro.",
                "Retirada na biblioteca ou entrega no bloco",
                variants=[("Simples", 800), ("Com nozes", 1000)],
            ),
            DemoOffer(
                "Bolo de pote do dia (exemplo)",
                "comidas-e-doces",
                D,
                1200,
                "O sabor muda todo dia; confirmo cedo se tem.",
                "Retirada no bloco 3, até as 18h",
                portion="1 pote de 250 ml",
                ingredients="Massa de baunilha, creme de leite, morango",
                allergens="Contém glúten, leite e ovos",
                confirmed_today=True,
                closing_time=time(18, 0),
            ),
            DemoOffer(
                "Torta de limão (exemplo)",
                "comidas-e-doces",
                R,
                1500,
                "Fatia generosa, com merengue maçaricado.",
                status=S.SOLD_OUT,
                portion="1 fatia",
            ),
        ],
    ),
    DemoSeller(
        key="pedro",
        name="Pedro do Brechó (exemplo)",
        bio="Vendo o que não uso mais. Exemplo de vendedor fictício.",
        area="Alojamento e campus",
        hours="Noites e fins de semana",
        trusted=True,
        offers=[
            DemoOffer(
                "Patinete usado (exemplo)",
                "objetos-e-usados",
                O,
                18000,
                "Patinete elétrico em bom estado, bateria nova.",
                "Retirada no estacionamento do campus",
                confirmed_days_ago=2,
            ),
            DemoOffer(
                "Apostila de Física 1 (exemplo)",
                "objetos-e-usados",
                O,
                2500,
                "Apostila encadernada, poucas anotações.",
                status=S.SOLD,
            ),
            DemoOffer(
                "Calculadora científica (exemplo)",
                "objetos-e-usados",
                O,
                4500,
                "Casio fx-82, funcionando perfeitamente.",
                confirmed_days_ago=20,
            ),
            DemoOffer(
                "Mochila (exemplo)",
                "objetos-e-usados",
                O,
                6000,
                "Mochila preta com compartimento para notebook.",
                status=S.PAUSED,
                confirmed_days_ago=1,
            ),
        ],
    ),
    DemoSeller(
        key="lucas",
        name="Lucas Monitor (exemplo)",
        bio="Monitoria de exatas entre colegas. Exemplo de vendedor fictício.",
        area="Biblioteca e online",
        hours="Combine pelo WhatsApp",
        trusted=True,
        offers=[
            DemoOffer(
                "Aula particular de Cálculo (exemplo)",
                "servicos",
                R,
                4000,
                "Cálculo 1 e 2, em grupo ou individual.",
                "Presencial na biblioteca ou online",
                variants=[("Individual", 4000), ("Dupla (por pessoa)", 2500)],
            ),
            DemoOffer(
                "Marmita do dia (exemplo)",
                "comidas-e-doces",
                D,
                1800,
                "Arroz, feijão, proteína do dia e salada.",
                "Retirada no bloco 3",
                portion="1 marmita de 500 g",
                ingredients="",
            ),
            DemoOffer(
                "Revisão de provas (exemplo)",
                "servicos",
                R,
                3000,
                "Revisão da matéria antes das provas, em grupo.",
                approval=Offer.Approval.PENDING,
            ),
        ],
    ),
    DemoSeller(
        key="novo",
        name="Loja Nova (exemplo)",
        bio="Vendedor fictício que ainda não teve o primeiro anúncio aprovado.",
        area="Campus",
        hours="",
        trusted=False,
        offers=[
            DemoOffer(
                "Suco natural (exemplo)",
                "bebidas",
                R,
                700,
                "Suco feito na hora, sem açúcar.",
                approval=Offer.Approval.PENDING,
                portion="Copo de 300 ml",
                ingredients="Laranja e limão",
            ),
            DemoOffer(
                "Capa de caderno (exemplo)",
                "outros",
                O,
                1000,
                "Capa dura para caderno universitário.",
                hidden=True,
            ),
        ],
    ),
]


class Command(BaseCommand):
    help = (
        "Carrega dados de demonstração (só com DEMO_DATA=true). "
        "Com --remove, apaga os dados de demonstração (funciona sem DEMO_DATA)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--remove",
            action="store_true",
            help="Apaga as contas @exemplo.invalid de demonstração, os anúncios e as fotos.",
        )

    def handle(self, *args, **options) -> None:
        if options["remove"]:
            self._remove()
            return
        if not settings.DEMO_DATA:
            raise CommandError("Recusado: defina DEMO_DATA=true para carregar dados de exemplo.")
        now = clock.now()
        today = now.astimezone(clock.community_tz()).date()
        categories = {c.slug: c for c in Category.objects.all()}
        missing = {o.category for s in SELLERS for o in s.offers} - set(categories)
        if missing:
            raise CommandError(f"Categorias ausentes: {', '.join(sorted(missing))}.")
        with transaction.atomic():
            for demo in SELLERS:
                seller = self._seller(demo)
                for item in demo.offers:
                    self._offer(seller, item, categories[item.category], now, today)
        self.stdout.write(
            f"Dados de exemplo carregados: {len(SELLERS)} vendedores, "
            f"{sum(len(s.offers) for s in SELLERS)} anúncios."
        )

    def _remove(self) -> None:
        """Apaga só contas `@exemplo.invalid` com perfil de demonstração (nunca staff).

        A cascata leva vendedor, anúncios, variações, fotos e métricas; os arquivos
        das fotos são apagados pelo `post_delete` (signals.py) depois do commit.
        """
        users = User.objects.filter(
            email__iendswith=f"@{DEMO_DOMAIN}",
            seller__is_demo=True,
            is_staff=False,
            is_superuser=False,
        )
        with transaction.atomic():
            offers = Offer.objects.filter(seller__user__in=users).count()
            count = users.count()
            users.delete()
        self.stdout.write(f"Dados de exemplo removidos: {count} contas, {offers} anúncios.")

    def _seller(self, demo: DemoSeller) -> Seller:
        email = f"demo-{demo.key}@{DEMO_DOMAIN}"
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email, password=None)  # senha inutilizável
        fields = {
            "display_name": demo.name,
            "bio": demo.bio,
            "service_area": demo.area,
            "hours": demo.hours,
            "whatsapp_number": "",
            "whatsapp_public": False,
            "is_trusted": demo.trusted,
            "is_demo": True,
        }
        seller = Seller.objects.filter(user=user).first()
        if seller is None:
            slug = unique_slug(Seller, demo.name, fallback="vendedor")
            return Seller.objects.create(user=user, slug=slug, **fields)
        for name, value in fields.items():
            setattr(seller, name, value)
        seller.save()
        return seller

    def _offer(self, seller: Seller, item: DemoOffer, category: Category, now, today) -> None:
        confirmed_at = now - timedelta(days=item.confirmed_days_ago)
        values = {
            "category": category,
            "kind": item.kind,
            "description": item.description,
            "price_cents": item.price_cents,
            "fulfillment": item.fulfillment,
            "portion": item.portion,
            "ingredients": item.ingredients,
            "allergens": item.allergens,
            "status": item.status,
            "status_changed_at": now,
            "approval": item.approval,
            "approved_at": now if item.approval == Offer.Approval.APPROVED else None,
            "hidden_at": now if item.hidden else None,
            "hidden_reason": "Exemplo de anúncio oculto pela administração." if item.hidden else "",
            "daily_confirmed_on": today if item.confirmed_today else None,
            "closing_time": item.closing_time,
            "last_confirmed_at": confirmed_at,
        }
        offer, _ = Offer.objects.update_or_create(seller=seller, title=item.title, defaults=values)
        offer.variants.all().delete()
        OfferVariant.objects.bulk_create(
            OfferVariant(offer=offer, name=name, price_cents=cents, position=position)
            for position, (name, cents) in enumerate(item.variants)
        )
