from django.contrib import admin

from .models import Analysis, ChatMessage, Decision, Document, Event, Finding, Region, RegulationRequest


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "short", "code", "grid_col", "grid_row")


class DocumentInline(admin.StackedInline):
    model = Document
    extra = 1
    fields = ("title", "kind", "file", "pages", "text", "order")


@admin.register(RegulationRequest)
class RegulationRequestAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "region", "district", "issuer_name", "doc_type", "status", "submitted_at")
    list_filter = ("status", "doc_type", "region", "category")
    search_fields = ("number", "draft_number", "title", "issuer_name", "district")
    date_hierarchy = "submitted_at"
    readonly_fields = ("number", "created_at", "updated_at")
    inlines = [DocumentInline]
    fieldsets = (
        (None, {"fields": ("number", "draft_number", "title", "doc_type", "category", "summary")}),
        ("Kimdan", {"fields": ("region", "district", "issuer_name", "issuer_title")}),
        ("Holat", {"fields": ("status", "submitted_at", "created_at", "updated_at")}),
    )


class FindingInline(admin.TabularInline):
    model = Finding
    extra = 0
    fields = ("severity", "category", "title", "law_ref")


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ("request", "state", "verdict", "score", "backend", "model_name", "started_at", "finished_at")
    list_filter = ("state", "verdict", "backend")
    search_fields = ("request__number", "request__title")
    readonly_fields = ("text_sha256", "rules_version", "steps", "checks", "sources")
    inlines = [FindingInline]


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ("request", "outcome", "ai_recommendation", "decided_by", "decided_at")
    list_filter = ("outcome",)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "request", "actor", "text")
    list_filter = ("kind",)


admin.site.register(ChatMessage)
