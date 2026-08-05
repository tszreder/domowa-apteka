import secrets
from typing import Iterable

from django.conf import settings
from django.db import models
from django.db.models.base import ModelBase


class Household(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    invite_token = models.CharField(max_length=64, unique=True, db_index=True, blank=True)

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        if not self.invite_token:
            self.invite_token = secrets.token_urlsafe(32)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def regenerate_invite_token(self) -> None:
        self.invite_token = secrets.token_urlsafe(32)
        self.save(update_fields=['invite_token'])

    def __str__(self) -> str:
        return self.name


class Membership(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='membership',
    )
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f'{self.user} in {self.household}'
