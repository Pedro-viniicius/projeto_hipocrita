"""Filtro de log que tira a mensagem das exceções de banco.

As mensagens do PostgreSQL/psycopg costumam trazer valores da query
(por exemplo, `Key (email)=(...) already exists`), que podem ser dado pessoal.
O filtro mantém o tipo da exceção e as linhas do traceback, sem a mensagem.
"""

import logging
import traceback

from django.db import DatabaseError

REDACTED = "(mensagem omitida: pode conter dados da consulta)"


def _chain(exc: BaseException | None):
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _is_db_error(exc: BaseException) -> bool:
    for item in _chain(exc):
        if isinstance(item, DatabaseError):
            return True
        module = type(item).__module__ or ""
        if module.startswith(("psycopg", "sqlite3")):
            return True
    return False


class RedactDatabaseErrors(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        exc_info = record.exc_info
        if exc_info and exc_info[1] is not None and _is_db_error(exc_info[1]):
            exc = exc_info[1]
            lines = ["Traceback (most recent call last):\n"]
            lines.extend(traceback.format_tb(exc.__traceback__))
            names = " <- ".join(type(item).__qualname__ for item in _chain(exc))
            lines.append(f"{names}: {REDACTED}")
            record.exc_info = None
            record.exc_text = "".join(lines)
        return True
