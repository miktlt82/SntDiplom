"""Analytics dashboard tab with charts."""

from __future__ import annotations
from tkinter import messagebox
import customtkinter as ctk

from app.gui.tabs.base_tab import BaseTab
from app.gui.widgets.progress_dialog import ProgressDialog
from app.logger import get_logger

logger = get_logger(__name__)
from app.gui.widgets.chart_frame import ChartFrame
from app.gui.widgets.styled_treeview import StyledTreeview
from app.services.report_service import (
    get_member_stats, get_membership_fee_summary, get_target_fee_summary,
    get_electricity_summary, get_debtors_list, get_payments_by_period,
    get_target_payments_by_campaign, get_electricity_payments_by_period,
)


DEBTORS_COLUMNS = [
    {"id": "plot_number", "text": "Участок", "width": 80, "anchor": "center"},
    {"id": "full_name", "text": "ФИО", "width": 250},
    {"id": "total_debt", "text": "Общий долг", "width": 120, "anchor": "e"},
]


class AnalyticsTab(BaseTab):

    def __init__(self, app):
        super().__init__(app)
        self._refresh_generation = 0
        self._last_data = None

    def _build_ui(self):
        # Scrollable container
        container = ctk.CTkScrollableFrame(self.frame)
        container.pack(fill="both", expand=True, padx=5, pady=5)

        # Summary cards row
        cards_frame = ctk.CTkFrame(container)
        cards_frame.pack(fill="x", pady=5)

        self.members_card = self._create_card(cards_frame, "Участники")
        self.mfee_card = self._create_card(cards_frame, "Членские взносы")
        self.tfee_card = self._create_card(cards_frame, "Целевые взносы")
        self.elec_card = self._create_card(cards_frame, "Электроэнергия")

        # Analytics selector
        selector_frame = ctk.CTkFrame(container)
        selector_frame.pack(fill="x", pady=(5, 0))

        ctk.CTkLabel(selector_frame, text="Графики:").pack(side="left", padx=5)
        self.analytics_scope_var = ctk.StringVar(value="Членские взносы")
        ctk.CTkOptionMenu(
            selector_frame,
            variable=self.analytics_scope_var,
            values=["Членские взносы", "Целевые взносы", "Электроэнергия"],
            command=lambda _: self._refresh_charts_from_cache(),
            width=220,
        ).pack(side="left", padx=5, pady=5)

        # Charts row
        charts_frame = ctk.CTkFrame(container)
        charts_frame.pack(fill="x", pady=5)

        self.pie_chart = ChartFrame(charts_frame, figsize=(4, 3))
        self.pie_chart.pack(side="left", fill="both", expand=True, padx=5)

        self.bar_chart = ChartFrame(charts_frame, figsize=(5, 3))
        self.bar_chart.pack(side="left", fill="both", expand=True, padx=5)

        # Debtors table
        ctk.CTkLabel(container, text="Должники", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=5, pady=(10, 5)
        )
        debtors_frame = ctk.CTkFrame(container, height=250)
        debtors_frame.pack(fill="x", padx=5, pady=5)
        debtors_frame.pack_propagate(False)

        self.debtors_tree = StyledTreeview(
            debtors_frame, columns=DEBTORS_COLUMNS,
            style_name="Debtors.Treeview",
        )
        self.debtors_tree.pack_with_scrollbar()

        # Refresh button
        ctk.CTkButton(container, text="Обновить", width=120,
                       command=self.refresh_data).pack(pady=10)

    def _create_card(self, parent, title: str) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(parent)
        frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(5, 0))
        label = ctk.CTkLabel(frame, text="—", font=ctk.CTkFont(size=11))
        label.pack(pady=(0, 5))
        return label

    def refresh_data(self):
        self._refresh_generation += 1
        current_gen = self._refresh_generation

        def _fetch_all():
            return {
                "members": get_member_stats(),
                "mfee": get_membership_fee_summary(),
                "tfee": get_target_fee_summary(),
                "elec": get_electricity_summary(),
                "debtors": get_debtors_list(),
                "periods": get_payments_by_period(),
                "campaigns": get_target_payments_by_campaign(),
                "electricity_periods": get_electricity_payments_by_period(),
            }

        def _on_success(data):
            if current_gen != self._refresh_generation:
                return  # stale result — DB was switched during fetch
            try:
                self._last_data = data
                self._apply_cards(data)
                self._apply_charts(data)
                self._apply_debtors(data)
            except Exception:
                logger.error("Analytics UI update failed", exc_info=True)

        ProgressDialog(
            self.app, "Обновление аналитики...",
            target=_fetch_all,
            on_success=_on_success,
            on_error=lambda e: (
                logger.error("Analytics refresh failed", exc_info=True),
                messagebox.showerror("Ошибка", "Не удалось обновить аналитику"),
            ),
        )

    def _apply_cards(self, data):
        ms = data["members"]
        self.members_card.configure(
            text=f"Всего: {ms['total']} | Акт.: {ms['active']} | Арх.: {ms['archived']}"
        )

        mf = data["mfee"]
        self.mfee_card.configure(
            text=f"Начисл: {mf['total_due']:.2f} | Оплач: {mf['total_paid']:.2f} | Долг: {mf['outstanding']:.2f}"
        )

        tf = data["tfee"]
        self.tfee_card.configure(
            text=f"Начисл: {tf['total_due']:.2f} | Оплач: {tf['total_paid']:.2f} | Долг: {tf['outstanding']:.2f}"
        )

        el = data["elec"]
        self.elec_card.configure(
            text=f"Начисл: {el['total_due']:.2f} | Оплач: {el['total_paid']:.2f} | Долг: {el['outstanding']:.2f}"
        )

    def _apply_charts(self, data):
        scope = self.analytics_scope_var.get()
        config = {
            "Членские взносы": {
                "summary": "mfee",
                "series": "periods",
                "pie_title": "Членские взносы (статусы)",
                "bar_title": "Оплаты по периодам",
            },
            "Целевые взносы": {
                "summary": "tfee",
                "series": "campaigns",
                "pie_title": "Целевые взносы (статусы)",
                "bar_title": "Оплаты по кампаниям",
            },
            "Электроэнергия": {
                "summary": "elec",
                "series": "electricity_periods",
                "pie_title": "Электроэнергия (статусы)",
                "bar_title": "Оплаты по месяцам",
            },
        }.get(scope)

        if not config:
            return

        summary = data[config["summary"]]
        self.pie_chart.pie_chart(
            labels=["Оплачено", "Переплата", "Частично", "Не оплачено"],
            values=[
                summary["paid_count"],
                summary.get("overpaid_count", 0),
                summary["partial_count"],
                summary["not_paid_count"],
            ],
            title=config["pie_title"],
            colors=["#28a745", "#17a2b8", "#ffc107", "#dc3545"],
        )

        series = data[config["series"]]
        if series:
            labels = [p["period"][:18] for p in series]
            paid = [p["total_paid"] for p in series]
            self.bar_chart.bar_chart(
                labels=labels, values=paid,
                title=config["bar_title"], ylabel="Руб."
            )
        else:
            self.bar_chart.clear()
            self.bar_chart.draw()

    def _refresh_charts_from_cache(self):
        if self._last_data:
            self._apply_charts(self._last_data)

    def _apply_debtors(self, data):
        debtors = data["debtors"]
        rows = []
        for d in debtors:
            rows.append({
                "id": d["member_id"],
                "plot_number": d["plot_number"],
                "full_name": d["full_name"],
                "total_debt": f"{d['total_debt']:.2f}",
                "tag": "not_paid",
            })
        self.debtors_tree.load_data(rows)

    def _subscribe_events(self):
        super()._subscribe_events()
        self._subscribe("fee_paid", lambda **kw: self.refresh_data())
        self._subscribe("member_updated", lambda **kw: self.refresh_data())
