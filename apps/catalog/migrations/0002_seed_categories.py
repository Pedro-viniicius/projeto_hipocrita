"""Semente das 5 categorias iniciais (docs/produto/decisoes.md, item 3).

"Comidas e doces" e "Bebidas" são alimento (`is_food`): mostram porção,
ingredientes e alergênicos. O admin pode editar tudo depois, sem código.
Reversível: desfazer apaga só as categorias da semente que não têm anúncios.
"""

from django.db import migrations

CATEGORIES = [
    # (nome, slug, posição, is_food)
    ("Comidas e doces", "comidas-e-doces", 1, True),
    ("Bebidas", "bebidas", 2, True),
    ("Serviços", "servicos", 3, False),
    ("Objetos e usados", "objetos-e-usados", 4, False),
    ("Outros", "outros", 5, False),
]


def seed(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    for name, slug, position, is_food in CATEGORIES:
        Category.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "position": position, "is_food": is_food, "is_active": True},
        )


def unseed(apps, schema_editor):
    Category = apps.get_model("catalog", "Category")
    slugs = [slug for _, slug, _, _ in CATEGORIES]
    Category.objects.filter(slug__in=slugs, offers__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
