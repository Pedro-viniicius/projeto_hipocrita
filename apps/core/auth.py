"""Decoradores de acesso. A autorização fica sempre no servidor (CA11)."""

from collections.abc import Callable
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import HttpRequest, HttpResponse


def seller_required(view: Callable) -> Callable:
    """Exige login e perfil de vendedor; põe o perfil em `request.seller`.

    Anônimo vai para `/entrar/?next=...`. Usuário sem perfil de vendedor
    (por exemplo, um admin criado com `createsuperuser`) recebe 403.
    """

    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        try:
            request.seller = user.seller
        except ObjectDoesNotExist:
            raise PermissionDenied from None
        return view(request, *args, **kwargs)

    return wrapped


def staff_required(view: Callable) -> Callable:
    """Exige `is_staff`: anônimo vai para `/entrar/`; logado sem permissão recebe 403."""

    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (user.is_active and user.is_staff):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped
