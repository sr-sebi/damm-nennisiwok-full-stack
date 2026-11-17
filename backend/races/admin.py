from django.contrib import admin

from races.models import (
    Channel,
    ChannelColumn,
    ImportBatch,
    Notification,
    Race,
    Registration,
    ValueAlias,
)


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "location", "capacity")
    search_fields = ("name",)
    readonly_fields = ("next_bib",)


class ChannelColumnInline(admin.TabularInline):
    model = ChannelColumn
    extra = 0


class ValueAliasInline(admin.TabularInline):
    model = ValueAlias
    extra = 0


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "kind", "format", "encoding", "delimiter")
    inlines = [ChannelColumnInline, ValueAliasInline]


@admin.register(ValueAlias)
class ValueAliasAdmin(admin.ModelAdmin):
    list_display = ("field", "source_value", "value", "channel")
    list_filter = ("field", "channel")


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("bib", "first_name", "last_name", "race", "channel", "status")
    list_filter = ("race", "status", "channel")
    search_fields = ("search_text", "email_norm")
    raw_id_fields = ("possible_duplicate_of",)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "race", "channel", "status", "processed_rows", "total_rows", "created_at")
    list_filter = ("status", "channel")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "status", "attempts", "next_attempt_at", "sent_at")
    list_filter = ("status", "provider")
    search_fields = ("idempotency_key",)
    raw_id_fields = ("registration",)
