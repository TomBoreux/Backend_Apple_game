from django.conf import settings
from django.core.files.base import ContentFile
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import timedelta
from html import escape
from hashlib import sha256
import math
import secrets
from .models import (
    User,
    Doctor,
    SeedLevel,
    FullReport,
)
from .models import GameApiTokenSession
from .report_charts import (
    ReportChartDependencyError,
    ReportChartError,
    full_report_stats,
    full_reports_charts,
    full_reports_global_stats,
    generate_full_report_chart,
    parse_full_report,
)

ACCESS_TOKEN_SALT = "gameapi.access_token"
REPORT_LEVEL_COUNT_WIDTH = 2
MIN_STUDY_LEVEL_COUNT = 3
STUDY_CLIENT_PLATFORM = "android"


def doctor_data(obj):
    return {
        "id": obj.id,
        "last_name": obj.last_name,
        "first_name": obj.first_name,
        "token": obj.token,
        "email": obj.email,
    }


def seed_level_data(obj):
    return {
        "id": obj.id,
        "name": obj.name,
        "file": obj.file.url if obj.file else None,
    }


def user_data(obj):
    doctor = obj.doctors.order_by("-id").first()
    doctors = [doctor_data(doctor_obj) for doctor_obj in obj.doctors.all()]

    return {
        "id": obj.id,
        "token": obj.token,
        "uuid": obj.uuid,
        "birth_year": obj.birth_year,
        "doctors": doctors,
        "latest_doctor_id": doctor.id if doctor else None,
        "latest_doctor_token": doctor.token if doctor else "",
        "doctor_key": doctor.token if doctor else "",
    }


def full_report_data(obj):
    return {
        "id": obj.id,
        "user": obj.user_id,
        "session_id": obj.session_id,
        "file": obj.file.url if obj.file else None,
        "date": obj.date,
        "app_version": obj.app_version,
        "app_version_code": obj.app_version_code,
        "level_generation_version": obj.level_generation_version,
        "client_platform": obj.client_platform,
        "seed_levels": [seed.id for seed in obj.seed_levels.all()],
    }


def user_age_at_report(report):
    if report.user.birth_year is None:
        return None

    return report.date.year - report.user.birth_year


def add_report_context_to_stats(stats, report):
    age = user_age_at_report(report)

    for level in stats["levels"]:
        level["report"] = report.id
        level["user"] = report.user_id
        level["age"] = age

    stats["charts"] = full_reports_charts(stats["levels"])
    return stats


def normalized_client_platform(value):
    return (value or "").strip().lower()


def is_study_client_platform(value):
    return normalized_client_platform(value) == STUDY_CLIENT_PLATFORM


def non_study_platform_reason(value):
    platform = (value or "").strip() or "inconnue"
    return (
        f"Rapport ignoré : plateforme {platform}, "
        f"plateforme requise {STUDY_CLIENT_PLATFORM}."
    )


def short_report_reason(level_count):
    return (
        f"Rapport ignoré : {level_count} niveau(x), "
        f"minimum requis {MIN_STUDY_LEVEL_COUNT}."
    )


def request_wants_html(request):
    if request.GET.get("format") == "json":
        return False

    accept = request.headers.get("Accept", "")
    return "text/html" in accept and "application/json" not in accept


def format_number(value, decimals=1):
    if value is None:
        return "-"

    rounded = round(value, decimals)
    if rounded == int(rounded):
        return str(int(rounded))

    return str(rounded)


def chart_scale(values, padding=0.0):
    values = [value for value in values if value is not None]
    if not values:
        return 0, 1

    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return minimum - 1, maximum + 1

    span = maximum - minimum
    return minimum - span * padding, maximum + span * padding


def svg_empty_chart(message):
    return (
        '<svg class="chart" viewBox="0 0 760 300" role="img">'
        '<text x="380" y="150" text-anchor="middle" class="empty">'
        f"{escape(message)}</text></svg>"
    )


def svg_level_percent_by_age(rows):
    rows = [row for row in rows if row["age"] is not None]
    if not rows:
        return svg_empty_chart("Aucune donnée d'âge disponible.")

    width = 760
    height = 320
    left = 58
    right = 24
    top = 30
    bottom = 54
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_value = max(row["average_movement_percent"] or 0 for row in rows)
    max_value = max(100, math.ceil(max_value / 10) * 10)
    bar_gap = 10
    bar_width = max(16, (chart_width - bar_gap * (len(rows) - 1)) / len(rows))

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />',
    ]

    for tick in range(0, int(max_value) + 1, max(10, int(max_value / 5))):
        y = height - bottom - (tick / max_value) * chart_height
        parts.append(f'<line class="grid" x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" />')
        parts.append(f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{tick}%</text>')

    for index, row in enumerate(rows):
        value = row["average_movement_percent"] or 0
        x = left + index * (bar_width + bar_gap)
        bar_height = (value / max_value) * chart_height
        y = height - bottom - bar_height
        label = format_number(value)
        parts.append(f'<rect class="bar" x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" rx="3" />')
        parts.append(f'<text x="{x + bar_width / 2}" y="{y - 8}" text-anchor="middle">{label}%</text>')
        parts.append(f'<text x="{x + bar_width / 2}" y="{height - bottom + 24}" text-anchor="middle">{row["age"]}</text>')

    parts.append(f'<text x="{width / 2}" y="{height - 8}" text-anchor="middle">Âge</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_score_by_age(rows):
    return svg_bar_chart(
        [
            {
                "label": row["age"] if row["age"] is not None else "Âge inconnu",
                "value": row["average_score"],
                "title": (
                    f"Âge {row['age']} : score moyen "
                    f"{format_number(row['average_score'], 2)} "
                    f"sur {row['level_count']} niveaux"
                ),
            }
            for row in rows
            if row["age"] is not None
        ],
        "Aucune donnée de score par âge disponible.",
        max_floor=3,
    )


def svg_stars_by_speed(points):
    if not points:
        return svg_empty_chart("Aucun niveau terminé avec étoiles disponible.")

    width = 760
    height = 320
    left = 58
    right = 24
    top = 24
    bottom = 54
    chart_width = width - left - right
    chart_height = height - top - bottom
    min_speed, max_speed = chart_scale([point["speed"] for point in points], padding=0.08)
    min_stars, max_stars = 0, max(3, max(point["stars"] for point in points))

    def x_pos(speed):
        return left + ((speed - min_speed) / (max_speed - min_speed)) * chart_width

    def y_pos(stars):
        return height - bottom - ((stars - min_stars) / (max_stars - min_stars)) * chart_height

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />',
    ]

    for stars in range(min_stars, max_stars + 1):
        y = y_pos(stars)
        parts.append(f'<line class="grid" x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" />')
        parts.append(f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{stars}</text>')

    for index in range(6):
        speed = min_speed + ((max_speed - min_speed) / 5) * index
        x = x_pos(speed)
        parts.append(f'<text x="{x}" y="{height - bottom + 24}" text-anchor="middle">{format_number(speed, 2)}</text>')

    for point in points:
        title = (
            f"Rapport {point['report']}, niveau {point['level']}, "
            f"vitesse {format_number(point['speed'], 2)}, étoiles {point['stars']}"
        )
        parts.append(
            f'<circle class="dot" cx="{x_pos(point["speed"])}" cy="{y_pos(point["stars"])}" r="5">'
            f"<title>{escape(title)}</title></circle>"
        )

    parts.append(f'<text x="{width / 2}" y="{height - 8}" text-anchor="middle">Vitesse</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_bar_chart(rows, empty_message, value_suffix="", max_floor=None):
    rows = [
        {
            "label": str(row["label"]),
            "value": row["value"] or 0,
            "title": row.get("title", ""),
        }
        for row in rows
    ]
    if not rows:
        return svg_empty_chart(empty_message)

    width = 760
    height = 320
    left = 58
    right = 24
    top = 30
    bottom = 58
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_value = max(row["value"] for row in rows)
    if max_floor is not None:
        max_value = max(max_floor, max_value)
    max_value = max(1, math.ceil(max_value / 10) * 10 if max_value > 10 else math.ceil(max_value))
    bar_gap = 10
    bar_width = max(16, (chart_width - bar_gap * (len(rows) - 1)) / len(rows))

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />',
    ]

    tick_step = max(1, int(max_value / 5))
    for tick in range(0, int(max_value) + 1, tick_step):
        y = height - bottom - (tick / max_value) * chart_height
        parts.append(f'<line class="grid" x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" />')
        parts.append(f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{tick}{escape(value_suffix)}</text>')

    for index, row in enumerate(rows):
        value = row["value"]
        x = left + index * (bar_width + bar_gap)
        bar_height = (value / max_value) * chart_height
        y = height - bottom - bar_height
        label = escape(format_number(value))
        title = escape(row["title"] or f"{row['label']}: {label}{value_suffix}")
        parts.append(f'<rect class="bar" x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" rx="3"><title>{title}</title></rect>')
        if len(rows) <= 18:
            parts.append(f'<text x="{x + bar_width / 2}" y="{y - 8}" text-anchor="middle">{label}{escape(value_suffix)}</text>')
        label_step = max(1, math.ceil(len(rows) / 12))
        if len(rows) <= 18 or index % label_step == 0:
            parts.append(f'<text x="{x + bar_width / 2}" y="{height - bottom + 24}" text-anchor="middle">{escape(row["label"][:10])}</text>')

    parts.append("</svg>")
    return "".join(parts)


def svg_line_chart(rows, empty_message, value_suffix="", max_floor=None):
    rows = [
        {
            "label": str(row["label"]),
            "value": row["value"] or 0,
            "title": row.get("title", ""),
        }
        for row in rows
    ]
    if not rows:
        return svg_empty_chart(empty_message)

    width = 760
    height = 320
    left = 58
    right = 24
    top = 30
    bottom = 58
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_value = max(row["value"] for row in rows)
    if max_floor is not None:
        max_value = max(max_floor, max_value)
    max_value = max(1, math.ceil(max_value / 10) * 10 if max_value > 10 else math.ceil(max_value))

    def x_pos(index):
        if len(rows) == 1:
            return left + chart_width / 2
        return left + (index / (len(rows) - 1)) * chart_width

    def y_pos(value):
        return height - bottom - (value / max_value) * chart_height

    points = " ".join(
        f'{x_pos(index)},{y_pos(row["value"])}'
        for index, row in enumerate(rows)
    )
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img">',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" />',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" />',
    ]

    tick_step = max(1, int(max_value / 5))
    for tick in range(0, int(max_value) + 1, tick_step):
        y = height - bottom - (tick / max_value) * chart_height
        parts.append(f'<line class="grid" x1="{left}" y1="{y}" x2="{width - right}" y2="{y}" />')
        parts.append(f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{tick}{escape(value_suffix)}</text>')

    parts.append(f'<polyline class="line" points="{points}" />')

    for index, row in enumerate(rows):
        x = x_pos(index)
        y = y_pos(row["value"])
        label = escape(format_number(row["value"]))
        title = escape(row["title"] or f"{row['label']}: {label}{value_suffix}")
        parts.append(f'<circle class="line-dot" cx="{x}" cy="{y}" r="4"><title>{title}</title></circle>')
        if len(rows) <= 16:
            parts.append(f'<text x="{x}" y="{height - bottom + 24}" text-anchor="middle">{escape(row["label"][:10])}</text>')

    parts.append("</svg>")
    return "".join(parts)


def level_chart_rows(levels, field):
    return [
        {
            "label": f"N{level['level']}",
            "value": level[field],
            "title": f"Niveau {level['level']}: {format_number(level[field], 2)}",
        }
        for level in levels
    ]


def completed_level_chart_rows(levels, field):
    return level_chart_rows(
        [level for level in levels if not level["is_interrupted"] and level[field] is not None],
        field,
    )


def completion_rate(stats):
    if not stats["level_count"]:
        return None
    return stats["completed_level_count"] / stats["level_count"] * 100


def stats_metric_items(stats, extra_items=None):
    metrics = extra_items or []
    metrics.extend(
        [
            ("Niveaux", stats["level_count"]),
            ("Mouvement moyen", f"{format_number(stats['average_movement_percent'])}%"),
            ("Vitesse moyenne", format_number(stats.get("average_speed"), 2)),
        ]
    )
    return metrics


def metrics_html(metrics):
    return "".join(
        '<article class="metric">'
        f'<span>{escape(str(label))}</span>'
        f'<strong>{escape(str(value))}</strong>'
        '</article>'
        for label, value in metrics
    )


def panel_html(title, body, description=""):
    description_html = (
        f'<p class="panel-description">{escape(description)}</p>'
        if description
        else ""
    )
    return (
        '<article class="panel">'
        f'<h2>{escape(title)}</h2>'
        f"{description_html}"
        f"{body}"
        '</article>'
    )


def stats_dashboard_html(title, subtitle, metrics, panels, json_href="?format=json"):
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; color: #172033; background: #f7f8fb; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    .meta {{ margin: 0 0 24px; color: #5f6878; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(145px, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .metric {{ background: white; border: 1px solid #e4e8f0; border-radius: 8px; padding: 14px; }}
    .metric span {{ display: block; color: #667085; font-size: 13px; margin-bottom: 6px; }}
    .metric strong {{ display: block; font-size: 23px; line-height: 1.1; }}
    .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 18px; }}
    .panel {{ background: white; border: 1px solid #e4e8f0; border-radius: 8px; padding: 18px; box-shadow: 0 8px 24px rgba(30, 42, 70, 0.06); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e4e8f0; padding: 8px 6px; vertical-align: top; }}
    th {{ color: #667085; font-weight: 600; }}
    .empty-text {{ margin: 0; color: #667085; }}
    .panel-description {{ margin: -6px 0 14px; color: #667085; font-size: 13px; line-height: 1.4; }}
    .id-list {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; }}
    .id-list li {{ border: 1px solid #d8dee9; border-radius: 999px; padding: 5px 9px; background: #f8fafc; font-size: 13px; }}
    .chart {{ width: 100%; height: auto; overflow: visible; }}
    svg line {{ stroke: #9aa4b2; stroke-width: 1; }}
    svg line.grid {{ stroke: #e5e9f0; }}
    svg text {{ fill: #4e5868; font-size: 12px; }}
    svg .bar {{ fill: #2f6f9f; }}
    svg .dot {{ fill: #d14f45; opacity: 0.82; }}
    svg .line {{ fill: none; stroke: #2f6f9f; stroke-width: 3; }}
    svg .line-dot {{ fill: #2f6f9f; stroke: white; stroke-width: 1.5; }}
    svg .empty {{ font-size: 15px; fill: #6b7280; }}
    a {{ color: #2f6f9f; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <p class="meta">{escape(subtitle)} <a href="{escape(json_href)}">Voir les données JSON</a></p>
    <section class="metrics">{metrics_html(metrics)}</section>
    <section class="charts">{"".join(panels)}</section>
  </main>
</body>
</html>"""


def full_report_stats_html(payload):
    stats = payload["stats"]
    levels = stats["levels"]
    subtitle = (
        f"Rapport {payload['id']} - utilisateur {payload['user']} - "
        f"session {payload['session_id']}"
    )
    metrics = stats_metric_items(
        stats,
        [
            ("Rapport", payload["id"]),
            ("Utilisateur", payload["user"]),
            ("Âge", levels[0].get("age") if levels else "-"),
        ],
    )
    panels = [
        panel_html(
            "Pourcentage de mouvement par niveau",
            svg_line_chart(
                level_chart_rows(levels, "movement_percent"),
                "Aucun niveau disponible.",
                "%",
                max_floor=100,
            ),
            "Montre, pour chaque niveau du rapport, la distance parcourue par rapport à la distance attendue pendant le temps jouable.",
        ),
        panel_html(
            "Nombre d'étoiles par niveau",
            svg_bar_chart(
                completed_level_chart_rows(levels, "score"),
                "Aucun niveau terminé avec étoiles disponible.",
                max_floor=3,
            ),
            "Compare le score obtenu à chaque niveau terminé du rapport.",
        ),
        panel_html(
            "Vitesse par niveau",
            svg_line_chart(
                level_chart_rows(levels, "speed"),
                "Aucune vitesse disponible.",
            ),
            "Affiche la vitesse moyenne du joueur à chaque niveau, calculée avec la distance parcourue divisée par le temps jouable.",
        ),
        panel_html(
            "Étoiles en fonction de la vitesse",
            svg_stars_by_speed(stats["charts"]["stars_by_speed"]),
            "Chaque point correspond à un niveau terminé : l'axe horizontal représente la vitesse moyenne, l'axe vertical le nombre d'étoiles.",
        ),
        panel_html(
            "Distance finale par niveau",
            svg_bar_chart(
                completed_level_chart_rows(levels, "final_distance"),
                "Aucune distance finale disponible.",
            ),
            "Indique la distance restante à la cible à la fin de chaque niveau terminé.",
        ),
    ]
    return stats_dashboard_html(
        "Stats du rapport",
        subtitle,
        metrics,
        panels,
    )


def excluded_full_report_stats_html(payload):
    reason = payload["reason"]
    metrics = [
        ("Rapport", payload["id"]),
        ("Utilisateur", payload["user"]),
        ("Plateforme", payload.get("client_platform") or "-"),
        ("Niveaux", payload.get("level_count", "-")),
        ("Statut", "Exclu"),
    ]
    panels = [
        panel_html(
            "Rapport exclu de l'étude",
            f'<p class="empty-text">{escape(reason)}</p>',
        )
    ]
    return stats_dashboard_html(
        "Stats du rapport",
        f"Rapport {payload['id']} - session {payload['session_id']}",
        metrics,
        panels,
    )


def issue_table_html(title, rows, empty_message):
    if not rows:
        return panel_html(title, f'<p class="empty-text">{escape(empty_message)}</p>')

    body = [
        '<table>',
        '<thead><tr><th>ID</th><th>Utilisateur</th><th>Session</th><th>Raison</th></tr></thead>',
        '<tbody>',
    ]
    for row in rows:
        reason = row.get("reason") or row.get("error") or "-"
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('id', '-')))}</td>"
            f"<td>{escape(str(row.get('user', '-')))}</td>"
            f"<td>{escape(str(row.get('session_id', '-')))}</td>"
            f"<td>{escape(str(reason))}</td>"
            "</tr>"
        )

    body.extend(["</tbody>", "</table>"])
    return panel_html(title, "".join(body))


def excluded_report_ids_html(rows):
    if not rows:
        return panel_html(
            "Rapports exclus de l'étude",
            '<p class="empty-text">Aucun rapport exclu par les critères de l\'étude.</p>',
        )

    ids = sorted(row.get("id") for row in rows if row.get("id") is not None)
    items = "".join(f"<li>{escape(str(report_id))}</li>" for report_id in ids)
    return panel_html(
        "Rapports exclus de l'étude",
        f'<ul class="id-list">{items}</ul>',
        "Seuls les identifiants sont affichés ici ; les détails restent disponibles dans le JSON.",
    )


def full_reports_stats_html(payload):
    stats = payload["stats"]
    charts = stats["charts"]
    subtitle = (
        f"{payload['parsed_report_count']} rapports analysés, "
        f"{payload['excluded_report_count']} exclus, "
        f"{payload['failed_report_count']} erreurs."
    )
    metrics = stats_metric_items(
        stats,
        [
            ("Rapports", payload["report_count"]),
            ("Rapports Android", payload["android_report_count"]),
            ("Rapports analysés", payload["parsed_report_count"]),
            ("Rapports exclus", payload["excluded_report_count"]),
            ("Rapports en erreur", payload["failed_report_count"]),
        ],
    )
    panels = [
        panel_html(
            "Pourcentage moyen des niveaux en fonction de l'âge",
            svg_level_percent_by_age(charts["level_percent_by_age"]),
            "Regroupe les niveaux des rapports analysés par âge et affiche le pourcentage moyen de mouvement pour chaque âge.",
        ),
        panel_html(
            "Score moyen en fonction de l'âge",
            svg_score_by_age(charts["score_by_age"]),
            "Regroupe les niveaux terminés des rapports analysés par âge et affiche le score moyen obtenu.",
        ),
        panel_html(
            "Nombre d'étoiles en fonction de la vitesse",
            svg_stars_by_speed(charts["stars_by_speed"]),
            "Chaque point correspond à un niveau terminé issu des rapports analysés : vitesse moyenne en abscisse, étoiles en ordonnée.",
        ),
        excluded_report_ids_html(payload["excluded_reports"]),
        issue_table_html(
            "Fichiers en erreur",
            payload["failed_reports"],
            "Aucun fichier en erreur.",
        ),
    ]
    return stats_dashboard_html(
        "Stats générales des rapports",
        subtitle,
        metrics,
        panels,
    )


def request_seed_levels(request):
    for field in ("seed_levels", "seeds", "seed"):
        seed_level_ids = request_data_values(request, field)
        if seed_level_ids:
            break
    else:
        return [], None


    try:
        ids = [int(seed_level_id) for seed_level_id in seed_level_ids]
    except (TypeError, ValueError):
        return [], "invalid"

    seed_levels = list(SeedLevel.objects.filter(id__in=ids))
    if len(seed_levels) != len(set(ids)):
        return [], "missing"

    return seed_levels, None


def request_data_values(request, field):
    if hasattr(request.data, "getlist"):
        values = request.data.getlist(field)
    else:
        value = request.data.get(field)
        values = [] if value in (None, "") else [value]

    parsed_values = []
    for value in values:
        if value in (None, ""):
            continue

        parsed_values.extend(
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        )

    return parsed_values


def dat_report_payload(text_content, require_count_match):
    lines = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not lines:
        return 0, [], "invalid"

    try:
        level_count = int(lines[0])
    except ValueError:
        return 0, [], "invalid"

    if level_count < 1:
        return 0, [], "invalid"

    try:
        index = 1
        blocks = []
        while index < len(lines):
            block, index = read_dat_level_block(
                lines,
                index,
            )
            blocks.append(block)
    except ValueError:
        return 0, [], "invalid"

    if require_count_match and len(blocks) != level_count:
        return 0, [], "invalid"

    if len(blocks) > level_count:
        return 0, [], "invalid"

    return level_count, blocks, None


def dat_report_blocks(text_content):
    _level_count, blocks, error = dat_report_payload(
        text_content,
        require_count_match=True,
    )
    return blocks, error


def read_dat_level_block(lines, index):
    start = index

    index = consume_dat_line(lines, index, int)
    index = consume_dat_line(lines, index, float)
    index = consume_dat_pair(lines, index, int)
    index = consume_dat_pair(lines, index, int)
    index = consume_dat_visual(lines, index)

    tree_count, index = read_dat_count(lines, index)
    for _tree_index in range(tree_count):
        index = consume_dat_pair(lines, index, int)

    position_count, index = read_dat_count(lines, index)
    for _position_index in range(position_count):
        index = consume_dat_pair(lines, index, float)

    remaining_lines = len(lines) - index
    if remaining_lines >= 2:
        index = consume_dat_line(lines, index, float)
        index = consume_dat_line(lines, index, int)
    elif remaining_lines == 0:
        pass
    else:
        raise ValueError

    return lines[start:index], index


def consume_dat_line(lines, index, parser):
    if index >= len(lines):
        raise ValueError

    parser(lines[index])
    return index + 1


def consume_dat_pair(lines, index, parser):
    if index >= len(lines):
        raise ValueError

    values = lines[index].split()
    if len(values) != 2:
        raise ValueError

    for value in values:
        parser(value)

    return index + 1


def consume_dat_visual(lines, index):
    if index >= len(lines):
        raise ValueError

    values = lines[index].split()
    if len(values) != 3:
        raise ValueError

    for value in values:
        int(value)

    return index + 1


def read_dat_count(lines, index):
    if index >= len(lines):
        raise ValueError

    count = int(lines[index])
    if count < 0:
        raise ValueError

    return count, index + 1


def uploaded_dat_blocks(uploaded_file):
    try:
        raw_content = uploaded_file.read()
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        text_content = raw_content.decode("utf-8")
        level_count, blocks, error = dat_report_payload(
            text_content,
            require_count_match=False,
        )
        return level_count, blocks, error
    except (AttributeError, UnicodeDecodeError, ValueError):
        return 0, [], "invalid"


def existing_dat_blocks(obj):
    if not obj.file:
        return [], None

    try:
        with obj.file.open("rb") as file_handle:
            text_content = file_handle.read().decode("utf-8")
            return dat_report_blocks(text_content)
    except (FileNotFoundError, UnicodeDecodeError, ValueError):
        return [], "invalid"


def append_report_dat(obj, current_blocks, uploaded_level_count, uploaded_blocks):
    new_blocks = new_report_blocks(current_blocks, uploaded_blocks)
    if not new_blocks:
        return

    expected_level_count = len(current_blocks) + len(new_blocks)
    if uploaded_level_count != expected_level_count:
        raise ValueError(
            "The uploaded report level-count header does not match the "
            "merged report level count."
        )

    filename = report_dat_filename(obj)
    if not obj.file:
        create_report_dat(obj, filename, uploaded_level_count, new_blocks)
        return

    appended_content = dat_blocks_content(new_blocks, include_count=False)

    with obj.file.open("r+b") as file_handle:
        header = file_handle.readline()
        if not header:
            raise ValueError("The existing report file has no level count.")

        header_text = header.decode("utf-8").rstrip("\r\n")
        new_header_text = format_level_count(uploaded_level_count, len(header_text))
        if len(new_header_text) > len(header_text):
            raise ValueError(
                "The existing report file level-count header is too short "
                "to append in place."
            )

        file_handle.seek(0)
        file_handle.write(new_header_text.encode("utf-8"))
        file_handle.seek(0, 2)
        if file_handle.tell() > 0:
            file_handle.seek(-1, 2)
            last_byte = file_handle.read(1)
            if last_byte not in (b"\n", b"\r"):
                file_handle.write(b"\n")
            else:
                file_handle.seek(0, 2)
        file_handle.write(appended_content)


def new_report_blocks(current_blocks, uploaded_blocks):
    seen_blocks = {dat_block_key(block) for block in current_blocks}
    new_blocks = []

    for block in uploaded_blocks:
        block_key = dat_block_key(block)
        if block_key in seen_blocks:
            continue

        seen_blocks.add(block_key)
        new_blocks.append(block)

    return new_blocks


def dat_block_key(block):
    return tuple(block)


def create_report_dat(obj, filename, level_count, blocks):
    content = dat_blocks_content(blocks, include_count=True, level_count=level_count)
    obj.file.save(filename, ContentFile(content), save=False)


def dat_blocks_content(blocks, include_count, level_count=None):
    lines = []
    if include_count:
        if level_count is None:
            level_count = len(blocks)
        lines.append(format_level_count(level_count, REPORT_LEVEL_COUNT_WIDTH))

    for block in blocks:
        lines.extend(block)

    if not lines:
        return b""

    return ("\n".join(lines) + "\n").encode("utf-8")


def format_level_count(count, width):
    return str(count).zfill(width)


def report_dat_filename(obj):
    session_id = get_valid_filename(str(obj.session_id or obj.pk or "report"))
    return f"report_{session_id}.dat"


def require_admin_access(request):
    if not request.user or not request.user.is_authenticated:
        return Response(
            {"error": "Please sign in with an admin account to continue."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not request.user.is_staff:
        return Response(
            {"error": "This action is reserved for staff accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return None


def bootstrap_token(request):
    return (
        request.headers.get("X-Game-Api-Key")
        or request.data.get("api_key")
        or request.query_params.get("api_key")
    )


def get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return ""

    return authorization[len(prefix):].strip()


def request_refresh_token(request):
    return (
        request.data.get("refresh_token")
        or request.headers.get("X-Refresh-Token")
        or request.query_params.get("refresh_token")
    )


def hash_token(raw_token):
    return sha256(raw_token.encode("utf-8")).hexdigest()


def get_access_token_expiry():
    return timezone.now() + timedelta(
        seconds=settings.GAME_API_ACCESS_TOKEN_LIFETIME_SECONDS
    )


def get_refresh_token_expiry():
    return timezone.now() + timedelta(
        seconds=settings.GAME_API_REFRESH_TOKEN_LIFETIME_SECONDS
    )


def build_access_token(session, expires_at):
    payload = {
        "type": "game_access",
        "session_id": session.id,
        "exp": int(expires_at.timestamp()),
    }
    return signing.dumps(payload, salt=ACCESS_TOKEN_SALT)


def create_token_payload(session):
    access_expires_at = get_access_token_expiry()
    refresh_token = secrets.token_urlsafe(48)

    # Refresh tokens are rotated on every call so a stolen old token quickly
    # becomes useless, while the mobile client can keep a short-lived session.
    session.refresh_token_hash = hash_token(refresh_token)
    session.expires_at = get_refresh_token_expiry()
    session.revoked_at = None
    session.save(
        update_fields=[
            "refresh_token_hash",
            "expires_at",
            "revoked_at",
            "last_used_at",
        ]
    )

    return {
        "access_token": build_access_token(session, access_expires_at),
        "access_token_expires_at": access_expires_at.isoformat(),
        "expires_in": settings.GAME_API_ACCESS_TOKEN_LIFETIME_SECONDS,
        "refresh_token": refresh_token,
        "refresh_token_expires_at": session.expires_at.isoformat(),
        "token_type": "Bearer",
    }


def validate_access_token(access_token):
    if not access_token:
        return None

    try:
        payload = signing.loads(access_token, salt=ACCESS_TOKEN_SALT)
    except signing.BadSignature:
        return None

    if payload.get("type") != "game_access":
        return None

    if int(payload.get("exp", 0)) <= int(timezone.now().timestamp()):
        return None

    session_id = payload.get("session_id")
    if not session_id:
        return None

    session = GameApiTokenSession.objects.filter(id=session_id).first()
    if not session or not session.is_active():
        return None

    session.touch()
    return session


def require_bootstrap_token(request):
    expected_token = settings.GAME_API_WRITE_TOKEN
    if not expected_token:
        return Response(
            {"error": "The game API is not ready to accept write requests yet."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    provided_token = str(bootstrap_token(request) or "")
    if secrets.compare_digest(provided_token, expected_token):
        return None

    return Response(
        {"error": "A valid bootstrap API key is required to create a session."},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def is_admin_request(request):
    return bool(
        request.user
        and request.user.is_authenticated
        and request.user.is_staff
    )


def require_game_access(request):
    if is_admin_request(request):
        return None

    session = validate_access_token(get_bearer_token(request))
    if session:
        request.game_api_session = session
        return None

    return Response(
        {"error": "Please provide a valid game access token or sign in as an admin."},
        status=status.HTTP_401_UNAUTHORIZED,
    )


def parse_birth_year(birth_year_value):
    if birth_year_value in (None, ""):
        return None

    try:
        return int(birth_year_value)
    except (TypeError, ValueError):
        return "invalid"


def doctor_from_request(request):
    doctor_token = request.data.get("doctor_token")
    if not doctor_token:
        return None, None

    try:
        doctor = Doctor.objects.get(token=doctor_token)
    except Doctor.DoesNotExist:
        return None, doctor_token

    return doctor, None


@api_view(["POST"])
def create_game_api_token(request):
    bootstrap_response = require_bootstrap_token(request)
    if bootstrap_response:
        return bootstrap_response

    session = GameApiTokenSession.objects.create(
        device_uuid=str(request.data.get("uuid", "")).strip(),
        user_agent=request.headers.get("User-Agent", "")[:255],
        refresh_token_hash=hash_token(secrets.token_urlsafe(48)),
        expires_at=get_refresh_token_expiry(),
    )
    payload = create_token_payload(session)
    payload["session_id"] = session.id
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def refresh_game_api_token(request):
    refresh_token = str(request_refresh_token(request) or "").strip()
    if not refresh_token:
        return Response(
            {"error": "A refresh_token is required to renew the game session."},
            status=400,
        )

    refresh_token_hash = hash_token(refresh_token)
    with transaction.atomic():
        session = (
            GameApiTokenSession.objects.select_for_update()
            .filter(refresh_token_hash=refresh_token_hash)
            .first()
        )

        if not session or not session.is_active():
            return Response(
                {"error": "This refresh token is invalid or has expired."},
                status=401,
            )

        payload = create_token_payload(session)
    payload["session_id"] = session.id
    return Response(payload)


@api_view(['GET', 'POST', 'DELETE'])
def user_api(request, id=None):
    if request.method == "GET":
        access_response = require_game_access(request)
        if access_response:
            return access_response
    elif request.method == "DELETE":
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                user = User.objects.get(id=id)
                return Response(user_data(user))
            except User.DoesNotExist:
                return Response(
                    {"error": "No user was found for this id."},
                    status=404,
                )

        token_filter = request.query_params.get("token")
        if token_filter:
            user = User.objects.filter(token=token_filter).order_by("id").first()
            if not user:
                return Response(
                    {"error": "No user was found for this token."},
                    status=404,
                )
            return Response(user_data(user))

        if not is_admin_request(request):
            return Response(
                {
                    "error": (
                        "Use a token filter when looking up users "
                        "from the game client."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        users = User.objects.all()
        return Response([user_data(user) for user in users])

    if request.method == 'POST':
        token_response = require_game_access(request)
        if token_response:
            return token_response

        token = request.data.get("token")
        uuid = request.data.get("uuid")
        birth_year = parse_birth_year(request.data.get("birth_year"))
        doctor, invalid_doctor_token = doctor_from_request(request)

        if not token:
            return Response(
                {"error": "A player token is required to create or update a user."},
                status=400,
            )

        if birth_year == "invalid":
            return Response(
                {"error": "birth_year must be a whole year, for example 2012."},
                status=400,
            )

        if invalid_doctor_token:
            return Response(
                {"error": "No doctor matches the doctor_token sent by the client."},
                status=404,
            )

        if token == "guest":
            # Guest mode is intentionally shared for quick trials.
            try:
                user = User.objects.get(token="guest")
            except User.DoesNotExist:
                user = User.objects.create(
                    token="guest",
                    uuid=None,
                    birth_year=birth_year,
                )

            if birth_year is not None:
                user.birth_year = birth_year
                user.save(update_fields=["birth_year"])

            if doctor:
                user.doctors.add(doctor)

            response_data = user_data(user)
            return Response(response_data)

        if not uuid:
            return Response(
                {"error": "A uuid is required for non-guest players."},
                status=400,
            )

        user = User.objects.filter(token=token).order_by("id").first()
        created = user is None

        if created:
            user = User.objects.create(
                token=token,
                uuid=uuid,
                birth_year=birth_year,
            )
        else:
            fields_to_update = []

            if user.uuid != uuid:
                user.uuid = uuid
                fields_to_update.append("uuid")

            if birth_year is not None and user.birth_year != birth_year:
                user.birth_year = birth_year
                fields_to_update.append("birth_year")

            if fields_to_update:
                user.save(update_fields=fields_to_update)

        if doctor:
            user.doctors.add(doctor)

        response_data = user_data(user)
        return Response(response_data)

    if request.method == 'DELETE':
        try:
            user = User.objects.get(id=id)
            user.delete()
            return Response({"message": "User deleted"})
        except User.DoesNotExist:
            return Response(
                {"error": "No user was found for this id."},
                status=404,
            )

@api_view(['GET', 'POST', 'DELETE'])
def doctor_api(request, id=None):
    if request.method == "GET":
        access_response = require_game_access(request)
        if access_response:
            return access_response
    else:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = Doctor.objects.get(id=id)
                return Response(doctor_data(obj))
            except Doctor.DoesNotExist:
                return Response(
                    {"error": "No doctor was found for this id."},
                    status=404,
                )

        token_filter = request.query_params.get("token")
        if token_filter:
            obj = Doctor.objects.filter(token=token_filter).first()
            if not obj:
                return Response(
                    {"error": "No doctor was found for this token."},
                    status=404,
                )
            return Response(doctor_data(obj))

        if not is_admin_request(request):
            return Response(
                {
                    "error": (
                        "Use a token filter when looking up doctors "
                        "from the game client."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response([doctor_data(obj) for obj in Doctor.objects.all()])

    if request.method == 'POST':
        required_fields = ("last_name", "first_name", "token", "email")
        missing_fields = [
            field for field in required_fields if not request.data.get(field)
        ]

        if missing_fields:
            return Response(
                {field: ["This field is required."] for field in missing_fields},
                status=400,
            )

        try:
            obj = Doctor.objects.create(
                last_name=request.data.get("last_name"),
                first_name=request.data.get("first_name"),
                token=request.data.get("token"),
                email=request.data.get("email"),
            )
        except IntegrityError:
            return Response(
                {"error": "A doctor already exists with this token or email."},
                status=400,
            )
        return Response(doctor_data(obj))

    if request.method == 'DELETE':
        try:
            obj = Doctor.objects.get(id=id)
            obj.delete()
            return Response({"message": "Doctor deleted"})
        except Doctor.DoesNotExist:
            return Response(
                {"error": "No doctor was found for this id."},
                status=404,
            )


@api_view(['GET', 'POST', 'DELETE'])
def seed_api(request, id=None):
    if request.method == "POST":
        token_response = require_game_access(request)
        if token_response:
            return token_response
    else:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = SeedLevel.objects.get(id=id)
                return Response(seed_level_data(obj))
            except SeedLevel.DoesNotExist:
                return Response(
                    {"error": "No seed level was found for this id."},
                    status=404,
                )
        return Response([seed_level_data(obj) for obj in SeedLevel.objects.all()])

    if request.method == 'POST':
        if not request.data.get("name"):
            return Response({"name": ["This field is required."]}, status=400)

        existing_seed = SeedLevel.objects.filter(name=request.data.get("name")).first()
        if existing_seed:
            return Response(seed_level_data(existing_seed))

        if not request.data.get("file"):
            return Response({"file": ["No file was submitted."]}, status=400)

        obj = SeedLevel.objects.create(
            name=request.data.get("name"),
            file=request.data.get("file"),
        )
        return Response(seed_level_data(obj))

    if request.method == 'DELETE':
        try:
            obj = SeedLevel.objects.get(id=id)
            obj.delete()
            return Response({"message": "Seed deleted"})
        except SeedLevel.DoesNotExist:
            return Response(
                {"error": "No seed level was found for this id."},
                status=404,
            )


@api_view(['GET', 'POST', 'DELETE'])
def full_report_api(request, id=None):
    if request.method in {"GET", "DELETE"}:
        admin_response = require_admin_access(request)
        if admin_response:
            return admin_response

    if request.method == 'GET':
        if id:
            try:
                obj = FullReport.objects.get(id=id)
                return Response(full_report_data(obj))
            except FullReport.DoesNotExist:
                return Response(
                    {"error": "No full report was found for this id."},
                    status=404,
                )
        return Response([full_report_data(obj) for obj in FullReport.objects.all()])

    if request.method == 'POST':
        token_response = require_game_access(request)
        if token_response:
            return token_response

        if not request.data.get("user"):
            return Response({"user": ["This field is required."]}, status=400)

        if not request.data.get("session_id"):
            return Response({"session_id": ["This field is required."]}, status=400)

        if not request.data.get("file"):
            return Response({"file": ["No file was submitted."]}, status=400)

        try:
            user = User.objects.get(id=int(request.data.get("user")))
        except (TypeError, ValueError, User.DoesNotExist):
            return Response(
                {"error": "No user was found for this id."},
                status=404,
            )

        seed_levels, seed_error = request_seed_levels(request)
        if seed_error == "invalid":
            return Response(
                {"error": "seed_levels must contain seed level ids."},
                status=400,
            )

        if seed_error == "missing":
            return Response(
                {"error": "No seed level was found for one of these ids."},
                status=404,
            )

        uploaded_file = request.data.get("file")
        uploaded_level_count, uploaded_blocks, upload_error = uploaded_dat_blocks(
            uploaded_file,
        )
        if upload_error == "invalid":
            return Response(
                {"file": ["The uploaded file must be a valid line-by-line .dat report."]},
                status=400,
            )

        app_version_code = request.data.get("app_version_code")
        if app_version_code in (None, ""):
            app_version_code = None
        else:
            try:
                app_version_code = int(app_version_code)
            except (TypeError, ValueError):
                return Response(
                    {"app_version_code": ["A valid integer is required."]},
                    status=400,
                )

        with transaction.atomic():
            obj = (
                FullReport.objects.select_for_update()
                .filter(user=user, session_id=request.data.get("session_id"))
                .first()
            )

            if not obj:
                obj = FullReport(
                    user=user,
                    session_id=request.data.get("session_id"),
                )

            current_blocks, current_error = existing_dat_blocks(obj)
            if current_error == "invalid":
                return Response(
                    {"file": ["The existing report file is not a valid .dat report."]},
                    status=400,
                )

            obj.app_version = request.data.get("app_version", "")
            obj.app_version_code = app_version_code
            obj.level_generation_version = request.data.get(
                "level_generation_version",
                "",
            )
            obj.client_platform = request.data.get("client_platform", "")

            if not obj.pk:
                obj.save()

            try:
                append_report_dat(
                    obj,
                    current_blocks,
                    uploaded_level_count,
                    uploaded_blocks,
                )
            except ValueError as exc:
                return Response({"file": [str(exc)]}, status=400)

            obj.save()
            obj.seed_levels.add(*seed_levels)

        return Response(full_report_data(obj))

    if request.method == 'DELETE':
        try:
            obj = FullReport.objects.get(id=id)
            obj.delete()
            return Response({"message": "Full report deleted"})
        except FullReport.DoesNotExist:
            return Response(
                {"error": "No full report was found for this id."},
                status=404,
            )


@api_view(["GET"])
def full_report_chart_api(request, id):
    admin_response = require_admin_access(request)
    if admin_response:
        return admin_response

    try:
        obj = FullReport.objects.select_related("user").get(id=id)
    except FullReport.DoesNotExist:
        return Response(
            {"error": "No full report was found for this id."},
            status=404,
        )

    return report_chart_response(obj, "full report")


@api_view(["GET"])
def full_reports_stats_api(request):
    admin_response = require_admin_access(request)
    if admin_response:
        return admin_response

    reports = (
        FullReport.objects
        .filter(file__gt="")
        .select_related("user")
        .prefetch_related("seed_levels")
    )
    parsed_reports = []
    failed_reports = []
    excluded_reports = []

    for report in reports:
        if not is_study_client_platform(report.client_platform):
            excluded_reports.append(
                {
                    "id": report.id,
                    "user": report.user_id,
                    "session_id": report.session_id,
                    "client_platform": report.client_platform,
                    "reason": non_study_platform_reason(report.client_platform),
                }
            )
            continue

        try:
            with report.file.open("r") as file_handle:
                levels = parse_full_report(file_handle)
        except (FileNotFoundError, UnicodeDecodeError, ReportChartError) as exc:
            failed_reports.append(
                {
                    "id": report.id,
                    "user": report.user_id,
                    "session_id": report.session_id,
                    "error": str(exc),
                }
            )
            continue

        if len(levels) < MIN_STUDY_LEVEL_COUNT:
            excluded_reports.append(
                {
                    "id": report.id,
                    "user": report.user_id,
                    "session_id": report.session_id,
                    "client_platform": report.client_platform,
                    "level_count": len(levels),
                    "reason": short_report_reason(len(levels)),
                }
            )
            continue

        stats = add_report_context_to_stats(full_report_stats(levels), report)
        parsed_reports.append(
            {
                "id": report.id,
                "user": report.user_id,
                "session_id": report.session_id,
                "date": report.date,
                "app_version": report.app_version,
                "app_version_code": report.app_version_code,
                "level_generation_version": report.level_generation_version,
                "client_platform": report.client_platform,
                "seed_levels": [seed.id for seed in report.seed_levels.all()],
                "stats": stats,
            }
        )

    payload = {
        "report_count": FullReport.objects.count(),
        "report_with_file_count": reports.count(),
        "android_report_count": sum(
            1
            for report in reports
            if is_study_client_platform(report.client_platform)
        ),
        "study_client_platform": STUDY_CLIENT_PLATFORM,
        "parsed_report_count": len(parsed_reports),
        "excluded_report_count": len(excluded_reports),
        "excluded_reports": excluded_reports,
        "failed_report_count": len(failed_reports),
        "failed_reports": failed_reports,
        "stats": full_reports_global_stats(parsed_reports),
        "reports": parsed_reports,
    }

    if request_wants_html(request):
        return HttpResponse(full_reports_stats_html(payload))

    return Response(payload)


@api_view(["GET"])
def full_report_stats_api(request, id):
    admin_response = require_admin_access(request)
    if admin_response:
        return admin_response

    try:
        obj = FullReport.objects.get(id=id)
    except FullReport.DoesNotExist:
        return Response(
            {"error": "No full report was found for this id."},
            status=404,
        )

    if not obj.file:
        return Response(
            {"error": "This full report has no file attached."},
            status=404,
        )

    if not is_study_client_platform(obj.client_platform):
        payload = {
            "id": obj.id,
            "user": obj.user_id,
            "session_id": obj.session_id,
            "date": obj.date,
            "app_version": obj.app_version,
            "app_version_code": obj.app_version_code,
            "level_generation_version": obj.level_generation_version,
            "client_platform": obj.client_platform,
            "seed_levels": [seed.id for seed in obj.seed_levels.all()],
            "excluded": True,
            "minimum_level_count": MIN_STUDY_LEVEL_COUNT,
            "study_client_platform": STUDY_CLIENT_PLATFORM,
            "reason": non_study_platform_reason(obj.client_platform),
        }

        if request_wants_html(request):
            return HttpResponse(excluded_full_report_stats_html(payload))

        return Response(payload)

    try:
        with obj.file.open("r") as file_handle:
            levels = parse_full_report(file_handle)
    except FileNotFoundError:
        return Response(
            {"error": "The full report file could not be found."},
            status=404,
        )
    except (UnicodeDecodeError, ReportChartError) as exc:
        return Response(
            {"error": f"The full report file could not be analyzed: {exc}"},
            status=400,
        )

    if len(levels) < MIN_STUDY_LEVEL_COUNT:
        payload = {
            "id": obj.id,
            "user": obj.user_id,
            "session_id": obj.session_id,
            "date": obj.date,
            "app_version": obj.app_version,
            "app_version_code": obj.app_version_code,
            "level_generation_version": obj.level_generation_version,
            "client_platform": obj.client_platform,
            "seed_levels": [seed.id for seed in obj.seed_levels.all()],
            "excluded": True,
            "level_count": len(levels),
            "minimum_level_count": MIN_STUDY_LEVEL_COUNT,
            "study_client_platform": STUDY_CLIENT_PLATFORM,
            "reason": short_report_reason(len(levels)),
        }

        if request_wants_html(request):
            return HttpResponse(excluded_full_report_stats_html(payload))

        return Response(payload)

    payload = {
        "id": obj.id,
        "user": obj.user_id,
        "session_id": obj.session_id,
        "date": obj.date,
        "app_version": obj.app_version,
        "app_version_code": obj.app_version_code,
        "level_generation_version": obj.level_generation_version,
        "client_platform": obj.client_platform,
        "seed_levels": [seed.id for seed in obj.seed_levels.all()],
        "stats": add_report_context_to_stats(full_report_stats(levels), obj),
    }

    if request_wants_html(request):
        return HttpResponse(full_report_stats_html(payload))

    return Response(payload)


def report_chart_response(obj, report_label):
    if not obj.file:
        return Response(
            {"error": f"This {report_label} has no file attached."},
            status=404,
        )

    try:
        with obj.file.open("r") as file_handle:
            chart = generate_full_report_chart(file_handle)
    except FileNotFoundError:
        return Response(
            {"error": f"The {report_label} file could not be found."},
            status=404,
        )
    except (UnicodeDecodeError, ReportChartError) as exc:
        if isinstance(exc, ReportChartDependencyError):
            return Response(
                {"error": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {"error": f"The {report_label} file could not be converted to a chart: {exc}"},
            status=400,
        )

    return HttpResponse(chart.getvalue(), content_type="image/png")
