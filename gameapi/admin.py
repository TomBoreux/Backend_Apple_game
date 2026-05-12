from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import get_valid_filename
from .models import (
    User,
    SeedLevel,
    FullReport,
    Doctor,
)


def report_download_filename(obj):
    session_id = get_valid_filename(str(obj.session_id or obj.pk or "report"))
    return f"report_{session_id}.dat"


class ReportDownloadAdminMixin:
    readonly_fields = ("download_file",)
    search_fields = ("session_id", "user__token", "user__uuid")

    def get_urls(self):
        opts = self.model._meta
        custom_urls = [
            path(
                "<int:object_id>/download/",
                self.admin_site.admin_view(self.download_view),
                name=f"{opts.app_label}_{opts.model_name}_download",
            ),
        ]
        return custom_urls + super().get_urls()

    def download_view(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None or not obj.file:
            raise Http404("Report file not found.")

        try:
            file_handle = obj.file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Report file not found.") from exc

        filename = self.download_filename(obj)
        return FileResponse(file_handle, as_attachment=True, filename=filename)

    @admin.display(description="Download .dat")
    def download_file(self, obj):
        if not obj.file:
            return "-"

        filename = self.download_filename(obj)
        opts = self.model._meta
        download_url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_download",
            args=[obj.pk],
        )
        return format_html(
            '<a href="{}">Download {}</a>',
            download_url,
            filename,
        )

    def download_filename(self, obj):
        return report_download_filename(obj)


@admin.register(FullReport)
class FullReportAdmin(ReportDownloadAdminMixin, admin.ModelAdmin):
    readonly_fields = ("download_file", "view_chart", "view_stats")
    list_display = (
        "id",
        "user",
        "session_id",
        "seed_level_list",
        "doctor_list",
        "app_version",
        "app_version_code",
        "level_generation_version",
        "client_platform",
        "date",
        "download_file",
        "view_chart",
        "view_stats",
    )
    list_filter = (
        "app_version",
        "app_version_code",
        "level_generation_version",
        "client_platform",
    )
    search_fields = (
        "session_id",
        "user__token",
        "user__uuid",
        "user__doctors__last_name",
        "user__doctors__first_name",
        "user__doctors__email",
    )
    date_hierarchy = "date"
    list_select_related = ("user",)
    raw_id_fields = ("user", "seed_levels")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("seed_levels", "user__doctors")
        )

    @admin.display(description="Seed")
    def seed_level_list(self, obj):
        names = [seed.name for seed in obj.seed_levels.all()]
        return ", ".join(names) if names else "-"

    @admin.display(description="Doctors")
    def doctor_list(self, obj):
        names = [str(doctor) for doctor in obj.user.doctors.all()]
        return ", ".join(names) if names else "-"

    @admin.display(description="Chart")
    def view_chart(self, obj):
        if not obj.pk:
            return "-"

        return format_html(
            '<a href="/api/full-report/{}/chart/" target="_blank">View chart</a>',
            obj.pk,
        )

    @admin.display(description="Stats")
    def view_stats(self, obj):
        if not obj.pk:
            return "-"

        return format_html(
            '<a href="/api/full-report/{}/stats/" target="_blank">View stats</a>',
            obj.pk,
        )


class FullReportInline(admin.TabularInline):
    model = FullReport
    fields = (
        "id",
        "session_id",
        "seed_level_list",
        "app_version",
        "app_version_code",
        "level_generation_version",
        "client_platform",
        "date",
        "download_file",
        "view_chart",
        "view_stats",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Seed")
    def seed_level_list(self, obj):
        names = [seed.name for seed in obj.seed_levels.all()]
        return ", ".join(names) if names else "-"

    @admin.display(description="Download .dat")
    def download_file(self, obj):
        if not obj.file:
            return "-"

        download_url = reverse(
            "admin:gameapi_fullreport_download",
            args=[obj.pk],
        )
        filename = report_download_filename(obj)
        return format_html(
            '<a href="{}">Download {}</a>',
            download_url,
            filename,
        )

    @admin.display(description="Chart")
    def view_chart(self, obj):
        if not obj.pk:
            return "-"

        return format_html(
            '<a href="/api/full-report/{}/chart/" target="_blank">View chart</a>',
            obj.pk,
        )

    @admin.display(description="Stats")
    def view_stats(self, obj):
        if not obj.pk:
            return "-"

        return format_html(
            '<a href="/api/full-report/{}/stats/" target="_blank">View stats</a>',
            obj.pk,
        )


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "token",
        "uuid",
        "birth_year",
        "doctor_list",
    )
    search_fields = (
        "token",
        "uuid",
        "doctors__last_name",
        "doctors__first_name",
        "doctors__email",
    )
    filter_horizontal = ("doctors",)
    inlines = (FullReportInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("doctors")

    @admin.display(description="Doctors")
    def doctor_list(self, obj):
        names = [str(doctor) for doctor in obj.doctors.all()]
        return ", ".join(names) if names else "-"


@admin.register(SeedLevel)
class SeedLevelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "file")
    search_fields = ("name", "file")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "last_name", "first_name", "email", "token")
    search_fields = ("last_name", "first_name", "email", "token")
