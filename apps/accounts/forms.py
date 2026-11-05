"""Formulários das contas. Nenhum deles registra e-mail, telefone ou senha em log."""

from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.text import slugify

from apps.accounts.models import User, normalize_email
from apps.accounts.phone import normalize_br_mobile
from apps.catalog.models import Seller
from apps.core import clock
from apps.core.text import unique_slug
from texts import accounts as texts

REQUIRED_MESSAGES = {"required": texts.REQUIRED}
EMAIL_MESSAGES = {"required": texts.REQUIRED, "invalid": texts.EMAIL_INVALID}
# Entrada do WhatsApp aceita máscara e espaços; o número guardado tem 13 dígitos.
WHATSAPP_MAX_LENGTH = 30


class NoLabelSuffixMixin:
    """Rótulos sem ":" no fim (a spec usa o rótulo puro acima do campo) e a lista
    de campos com erro para o resumo no topo do formulário."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    @property
    def fields_with_errors(self) -> list:
        return [field for field in self if field.errors]


def _translate_password_errors(error: ValidationError) -> ValidationError:
    """Troca a mensagem de senha curta pela da spec; mantém as outras do Django."""
    messages = []
    for item in error.error_list:
        if item.code == "password_too_short":
            messages.append(ValidationError(texts.PASSWORD_TOO_SHORT, code=item.code))
        else:
            messages.append(item)
    return ValidationError(messages)


def _email_field(autocomplete: str = "email") -> forms.EmailField:
    return forms.EmailField(
        label=texts.EMAIL_LABEL,
        max_length=254,
        error_messages=EMAIL_MESSAGES,
        widget=forms.EmailInput(attrs={"autocomplete": autocomplete, "autocapitalize": "none"}),
    )


def _password_field(label: str, autocomplete: str, help_text: str = "") -> forms.CharField:
    return forms.CharField(
        label=label,
        help_text=help_text,
        strip=False,
        max_length=128,
        error_messages=REQUIRED_MESSAGES,
        widget=forms.PasswordInput(
            attrs={"autocomplete": autocomplete, "data-mostrar-senha": ""}, render_value=False
        ),
    )


class SignupForm(NoLabelSuffixMixin, forms.Form):
    """Cadastro de vendedor (CA6, CA8). Autorização do WhatsApp desmarcada por padrão."""

    display_name = forms.CharField(
        label=texts.NAME_LABEL,
        help_text=texts.NAME_HELP,
        max_length=Seller._meta.get_field("display_name").max_length,
        error_messages=REQUIRED_MESSAGES,
        widget=forms.TextInput(attrs={"autocomplete": "organization"}),
    )
    email = _email_field()
    password = _password_field(texts.PASSWORD_LABEL, "new-password", texts.PASSWORD_HELP)
    whatsapp = forms.CharField(
        label=texts.WHATSAPP_LABEL,
        help_text=texts.WHATSAPP_HELP,
        max_length=WHATSAPP_MAX_LENGTH,
        error_messages={"required": texts.REQUIRED, "max_length": texts.WHATSAPP_INVALID},
        widget=forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "tel"}),
    )
    whatsapp_public = forms.BooleanField(
        label=texts.WHATSAPP_PUBLIC_LABEL,
        help_text=texts.WHATSAPP_PUBLIC_HELP,
        required=False,
        initial=False,
    )

    def clean_display_name(self) -> str:
        name = " ".join(self.cleaned_data["display_name"].split())
        if not slugify(name):
            raise ValidationError(texts.NAME_INVALID, code="invalid")
        return name

    def clean_email(self) -> str:
        email = normalize_email(self.cleaned_data["email"])
        # `.invalid` é reservado (RFC 6761) e usado nas contas de exemplo: uma conta
        # real com esse domínio poderia ser tomada por `load_demo`.
        if email.lower().endswith(".invalid"):
            raise ValidationError(texts.EMAIL_INVALID, code="invalid")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(texts.EMAIL_TAKEN, code="email_taken")
        return email

    def clean_whatsapp(self) -> str:
        number = normalize_br_mobile(self.cleaned_data["whatsapp"])
        if number is None:
            raise ValidationError(texts.WHATSAPP_INVALID, code="invalid")
        return number

    def clean(self) -> dict:
        data = super().clean()
        password = data.get("password")
        if password:
            # Usuário provisório para o validador de semelhança com o e-mail.
            candidate = User(email=data.get("email") or "")
            try:
                password_validation.validate_password(password, candidate)
            except ValidationError as exc:
                self.add_error("password", _translate_password_errors(exc))
        return data

    def save(self) -> User | None:
        """Cria `User` e `Seller` numa transação. `None` se o e-mail foi usado
        por outro cadastro ao mesmo tempo (o erro vai para o campo)."""
        data = self.cleaned_data
        now = clock.now()
        try:
            with transaction.atomic():
                user = User.objects.create_user(email=data["email"], password=data["password"])
                Seller.objects.create(
                    user=user,
                    display_name=data["display_name"],
                    slug=unique_slug(Seller, data["display_name"], fallback="vendedor"),
                    whatsapp_number=data["whatsapp"],
                    whatsapp_public=data["whatsapp_public"],
                    whatsapp_public_changed_at=now if data["whatsapp_public"] else None,
                )
        except IntegrityError:
            if User.objects.filter(email__iexact=data["email"]).exists():
                self.add_error("email", ValidationError(texts.EMAIL_TAKEN, code="email_taken"))
                return None
            raise
        return user


class LoginForm(NoLabelSuffixMixin, forms.Form):
    """Login por e-mail. A falha tem uma só mensagem, que não diz qual campo errou."""

    email = _email_field()
    password = _password_field(texts.PASSWORD_LABEL, "current-password")

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict:
        data = super().clean()
        email, password = data.get("email"), data.get("password")
        if email and password:
            # O ModelBackend recusa conta inativa e roda o hasher mesmo quando o
            # e-mail não existe (o tempo de resposta não revela a conta).
            self.user = authenticate(self.request, email=normalize_email(email), password=password)
            if self.user is None:
                raise ValidationError(texts.LOGIN_FAILED, code="invalid_login")
        return data


class ResetRequestForm(NoLabelSuffixMixin, PasswordResetForm):
    email = _email_field()


class NewPasswordMixin:
    """Rótulos da spec e erros de força da senha no campo "Nova senha"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        first, second = self.fields["new_password1"], self.fields["new_password2"]
        first.label, first.help_text = texts.NEW_PASSWORD_LABEL, texts.PASSWORD_HELP
        second.label, second.help_text = texts.NEW_PASSWORD_CONFIRM_LABEL, ""
        for field in (first, second):
            field.error_messages["required"] = texts.REQUIRED
            field.widget.attrs["data-mostrar-senha"] = ""

    def validate_password_for_user(self, user, password_field_name=None):
        # O Django valida no campo de confirmação; aqui o erro fica junto da nova senha.
        password = self.cleaned_data.get("new_password1")
        if password:
            try:
                password_validation.validate_password(password, user)
            except ValidationError as exc:
                self.add_error("new_password1", _translate_password_errors(exc))


class NewPasswordForm(NoLabelSuffixMixin, NewPasswordMixin, SetPasswordForm):
    pass


class ChangePasswordForm(NoLabelSuffixMixin, NewPasswordMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        old = self.fields["old_password"]
        old.label = texts.OLD_PASSWORD_LABEL
        old.error_messages["required"] = texts.REQUIRED
        old.widget.attrs.pop("autofocus", None)
        old.widget.attrs["data-mostrar-senha"] = ""


class DeleteAccountForm(NoLabelSuffixMixin, forms.Form):
    """Confirmação da exclusão com a senha da conta."""

    password = _password_field(texts.DELETE_PASSWORD_LABEL, "current-password")

    def __init__(self, user: User, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self) -> str:
        password = self.cleaned_data["password"]
        if not self.user.check_password(password):
            raise ValidationError(texts.DELETE_WRONG_PASSWORD, code="wrong_password")
        return password
