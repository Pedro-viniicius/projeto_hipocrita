"""Formulário de denúncia do visitante (CA12). Sem nome, e-mail nem IP de quem denuncia."""

from django import forms

from apps.moderation.models import Report
from texts import public as texts

DETAILS_MAX_LENGTH = Report._meta.get_field("details").max_length


class ReportForm(forms.Form):
    reason = forms.ChoiceField(
        label=texts.REPORT_REASON_LABEL,
        choices=[(value, texts.REPORT_REASONS[value]) for value in Report.Reason.values],
        widget=forms.RadioSelect,
        error_messages={
            "required": texts.REPORT_REASON_REQUIRED,
            "invalid_choice": texts.REPORT_REASON_INVALID,
        },
    )
    details = forms.CharField(
        label=texts.REPORT_DETAILS_LABEL,
        help_text=texts.REPORT_DETAILS_HELP,
        required=False,
        max_length=DETAILS_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 4}),
        error_messages={"max_length": texts.REPORT_DETAILS_TOO_LONG},
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)

    @property
    def fields_with_errors(self) -> list:
        return [field for field in self if field.errors]

    def save(self, offer) -> Report:
        return Report.objects.create(
            offer=offer,
            reason=self.cleaned_data["reason"],
            details=self.cleaned_data["details"].strip(),
        )
