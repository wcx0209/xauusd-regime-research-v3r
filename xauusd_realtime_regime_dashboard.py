from __future__ import annotations

import argparse
import queue
import threading
from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, TOP, VERTICAL, Button, Frame, Label, StringVar, Text, Tk, ttk

from xauusd_realtime_regime_identifier import ROOT, build_bundles, run_once


DEFAULT_CALENDAR_PATH = ROOT / "data" / "codex_native_calendar_majors.csv"


FEATURE_LABELS = {
    "prev_day_range_ratio": "前一日波动幅度",
    "min_prev_extreme_dist_norm": "距前日极值距离",
    "OPEN_OUTSIDE_PREV_RANGE": "今日开盘是否跳出前日区间",
    "range_ratio_europe": "欧洲时段扩张幅度",
    "body_ratio_europe": "欧洲时段实体强度",
    "body_ratio_asia": "亚洲时段实体强度",
    "london2h_range_ratio": "伦敦前两小时扩张",
    "london2h_break_prevday": "伦敦盘是否突破前日高低",
    "us2h_range_ratio": "美盘前两小时扩张",
    "vix_abs_z20_lag1": "前一日VIX冲击强度",
    "tnx_abs_z20_lag1": "前一日美债收益率冲击",
    "oil_abs_z20_lag1": "前一日原油冲击",
    "dxy_abs_z20_lag1": "前一日美元指数冲击",
    "gld_abs_z20": "GLD波动强度",
    "gld_flow_proxy": "GLD资金流代理",
    "gc_volume_ratio20_lag1": "COMEX成交放量",
    "gvz_abs_z20_lag1": "黄金隐波GVZ冲击",
    "jpy_ret_lag1": "日元避险流向",
    "gold_vol_credit_intensity_lag1": "黄金-波动-信用联动强度",
    "FED_POLICY_rows": "联储政策事件",
    "US_INFLATION_rows": "美国通胀事件",
    "usd_high_total_rows": "美元高影响数据密度",
    "geo_total_score_z20_abs": "地缘冲击总强度",
    "GEO_MIDDLE_EAST_score_z20_abs": "中东地缘冲击",
    "WEEKEND_GEO_CARRY": "周末地缘冲击延续",
}


FEATURE_MEANINGS = {
    "prev_day_range_ratio": "衡量昨天的实际波动相对近期均值是偏大还是偏小。",
    "min_prev_extreme_dist_norm": "衡量现价离昨天高点或低点有多近，越近说明关键位压力更直接。",
    "OPEN_OUTSIDE_PREV_RANGE": "看今天开盘是否直接跳到昨天区间外，常见于隔夜冲击延续。",
    "range_ratio_europe": "看欧洲时段是否已经开始把日内波动拉开。",
    "body_ratio_europe": "看欧洲时段K线实体是否明显，实体越强越像单边推进。",
    "body_ratio_asia": "看亚洲盘是否已经出现方向性实体，而不是纯横盘。",
    "london2h_range_ratio": "看伦敦开盘后前两小时有没有明显扩张。",
    "london2h_break_prevday": "看伦敦盘是否直接打穿昨天高点或低点。",
    "us2h_range_ratio": "看美盘开盘后的前两小时是否进一步放大波动。",
    "vix_abs_z20_lag1": "看前一天风险恐慌是否异常，常影响黄金第二天的扩张概率。",
    "tnx_abs_z20_lag1": "看前一天美债收益率变动是否超常，常影响黄金利率敏感性。",
    "oil_abs_z20_lag1": "看前一天原油是否异常波动，常作为通胀与风险偏好的侧面代理。",
    "dxy_abs_z20_lag1": "看前一天美元是否异常波动，美元冲击往往会改变黄金日内节奏。",
    "gld_abs_z20": "看GLD的波动是否异常，反映黄金相关资金是否活跃。",
    "gld_flow_proxy": "看GLD方向性变化，近似反映ETF资金偏向。",
    "gc_volume_ratio20_lag1": "看COMEX黄金期货成交量是否高于近期常态。",
    "gvz_abs_z20_lag1": "看黄金期权隐含波动率是否出现异常。",
    "jpy_ret_lag1": "看前一天日元是否明显走强或走弱，反映避险资金是否在切换。",
    "gold_vol_credit_intensity_lag1": "看黄金、波动率与信用风险是否同时共振。",
    "FED_POLICY_rows": "看今天是否有联储政策相关事件进入高影响区间。",
    "US_INFLATION_rows": "看今天是否有美国通胀数据事件进入高影响区间。",
    "usd_high_total_rows": "看今天美元相关高影响事件数量是否偏多。",
    "geo_total_score_z20_abs": "看近期地缘新闻冲击是否显著高于平时。",
    "GEO_MIDDLE_EAST_score_z20_abs": "看中东方向的地缘升级是否明显。",
    "WEEKEND_GEO_CARRY": "看周末爆发的地缘事件是否顺延到本交易日定价。",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Desktop dashboard for the XAUUSD realtime regime identifier.")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--bars", type=int, default=12000)
    parser.add_argument("--terminal-path", default=r"C:\MT5PortableCodex\terminal64.exe")
    parser.add_argument(
        "--calendar-path",
        default=str(DEFAULT_CALENDAR_PATH),
    )
    parser.add_argument("--outdir", default="artifacts_xauusd_realtime_regime_identifier")
    parser.add_argument("--interval-minutes", type=float, default=5.0)
    parser.add_argument("--title", default="XAUUSD Realtime Regime")
    return parser.parse_args()


class RegimeDashboard:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.outdir = ROOT / args.outdir
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.snapshot_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.bundles = None
        self.refresh_job: str | None = None
        self.countdown_job: str | None = None
        self.next_refresh_at: datetime | None = None
        self.running = False

        self.root = Tk()
        self.root.title(args.title)
        self.root.geometry("980x760")
        self.root.minsize(900, 680)
        self.root.configure(bg="#f3efe7")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Card.TFrame", background="#fffaf1")
        style.configure("Section.TLabel", background="#fffaf1", foreground="#33261a", font=("Segoe UI Semibold", 10))
        style.configure("Value.TLabel", background="#fffaf1", foreground="#20160c", font=("Segoe UI", 11))

        self.status_var = StringVar(value="Loading models...")
        self.stage_var = StringVar(value="--")
        self.label_var = StringVar(value="--")
        self.high_vol_var = StringVar(value="--")
        self.trend_var = StringVar(value="--")
        self.regime_score_var = StringVar(value="--")
        self.generated_var = StringVar(value="--")
        self.next_var = StringVar(value="--")
        self.mode_var = StringVar(value="Waiting for first snapshot")

        self.header_label: Label | None = None
        self.driver_text: Text | None = None
        self.event_text: Text | None = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._start_bundle_load()
        self._poll_queue()

    def _build_ui(self) -> None:
        outer = Frame(self.root, bg="#f3efe7", padx=18, pady=16)
        outer.pack(fill=BOTH, expand=True)

        title = Label(
            outer,
            text="XAUUSD Realtime Regime Monitor",
            bg="#f3efe7",
            fg="#24170c",
            font=("Segoe UI Semibold", 22),
            anchor="w",
        )
        title.pack(fill="x")

        subtitle = Label(
            outer,
            text="V3R regularized model | auto refresh every 5 minutes | stage-aware regime classification",
            bg="#f3efe7",
            fg="#6b5742",
            font=("Segoe UI", 10),
            anchor="w",
            pady=4,
        )
        subtitle.pack(fill="x")

        hero = Frame(outer, bg="#fffaf1", highlightbackground="#d6c5af", highlightthickness=1, padx=16, pady=14)
        hero.pack(fill="x", pady=(12, 10))

        self.header_label = Label(
            hero,
            textvariable=self.label_var,
            bg="#fffaf1",
            fg="#6a4a1e",
            font=("Segoe UI Semibold", 26),
            anchor="w",
        )
        self.header_label.pack(fill="x")

        mode_label = Label(
            hero,
            textvariable=self.mode_var,
            bg="#fffaf1",
            fg="#3f2d18",
            font=("Segoe UI", 11),
            anchor="w",
            pady=2,
        )
        mode_label.pack(fill="x")

        meta = Frame(hero, bg="#fffaf1")
        meta.pack(fill="x", pady=(8, 0))
        Label(meta, text="Stage", bg="#fffaf1", fg="#7a6347", font=("Segoe UI", 10)).pack(side=LEFT)
        Label(meta, textvariable=self.stage_var, bg="#fffaf1", fg="#20160c", font=("Segoe UI Semibold", 10)).pack(side=LEFT, padx=(8, 18))
        Label(meta, text="Updated", bg="#fffaf1", fg="#7a6347", font=("Segoe UI", 10)).pack(side=LEFT)
        Label(meta, textvariable=self.generated_var, bg="#fffaf1", fg="#20160c", font=("Segoe UI Semibold", 10)).pack(side=LEFT, padx=(8, 18))
        Label(meta, text="Next refresh", bg="#fffaf1", fg="#7a6347", font=("Segoe UI", 10)).pack(side=LEFT)
        Label(meta, textvariable=self.next_var, bg="#fffaf1", fg="#20160c", font=("Segoe UI Semibold", 10)).pack(side=LEFT, padx=(8, 0))

        metrics = Frame(outer, bg="#f3efe7")
        metrics.pack(fill="x", pady=(0, 10))

        self._metric_card(metrics, "High Volatility Probability", self.high_vol_var).pack(side=LEFT, fill="both", expand=True, padx=(0, 8))
        self._metric_card(metrics, "Trend Probability", self.trend_var).pack(side=LEFT, fill="both", expand=True, padx=8)
        self._metric_card(metrics, "Regime Score", self.regime_score_var).pack(side=LEFT, fill="both", expand=True, padx=(8, 0))

        lower = Frame(outer, bg="#f3efe7")
        lower.pack(fill=BOTH, expand=True)

        structural_card = Frame(lower, bg="#fffaf1", highlightbackground="#d6c5af", highlightthickness=1, padx=12, pady=12)
        structural_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        Label(structural_card, text="Top Structural Drivers", bg="#fffaf1", fg="#2d2116", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        self.driver_text = self._make_text(structural_card)
        self.driver_text.pack(fill=BOTH, expand=True, pady=(10, 0))

        event_card = Frame(lower, bg="#fffaf1", highlightbackground="#d6c5af", highlightthickness=1, padx=12, pady=12)
        event_card.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))
        Label(event_card, text="Top Event Drivers", bg="#fffaf1", fg="#2d2116", font=("Segoe UI Semibold", 12)).pack(anchor="w")
        self.event_text = self._make_text(event_card)
        self.event_text.pack(fill=BOTH, expand=True, pady=(10, 0))

        footer = Frame(outer, bg="#f3efe7")
        footer.pack(fill="x", pady=(10, 0))
        Button(
            footer,
            text="Refresh Now",
            command=self._manual_refresh,
            bg="#b16a1f",
            fg="white",
            activebackground="#8c5318",
            activeforeground="white",
            relief="flat",
            padx=16,
            pady=8,
            font=("Segoe UI Semibold", 10),
        ).pack(side=LEFT)
        Label(footer, textvariable=self.status_var, bg="#f3efe7", fg="#5b4d3a", font=("Segoe UI", 10), anchor="w").pack(side=LEFT, padx=(14, 0))

    def _metric_card(self, parent: Frame, title: str, variable: StringVar) -> Frame:
        card = Frame(parent, bg="#fffaf1", highlightbackground="#d6c5af", highlightthickness=1, padx=14, pady=14)
        Label(card, text=title, bg="#fffaf1", fg="#755d40", font=("Segoe UI", 10), anchor="w").pack(fill="x")
        Label(card, textvariable=variable, bg="#fffaf1", fg="#20160c", font=("Segoe UI Semibold", 22), anchor="w", pady=8).pack(fill="x")
        return card

    def _make_text(self, parent: Frame) -> Text:
        text = Text(
            parent,
            wrap="word",
            height=18,
            bg="#fffaf1",
            fg="#22180f",
            relief="flat",
            font=("Segoe UI", 10),
            padx=4,
            pady=4,
        )
        text.configure(state="disabled")
        return text

    def _start_bundle_load(self) -> None:
        self.status_var.set("Loading V3R models...")
        thread = threading.Thread(target=self._load_bundles_worker, daemon=True)
        thread.start()

    def _load_bundles_worker(self) -> None:
        try:
            bundles = build_bundles()
        except Exception as exc:
            self.snapshot_queue.put(("error", f"Failed to load models: {exc}"))
            return
        self.snapshot_queue.put(("bundles_loaded", bundles))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.snapshot_queue.get_nowait()
                if kind == "bundles_loaded":
                    self.bundles = payload
                    self.status_var.set("Models loaded. Running first snapshot...")
                    self._schedule_immediate_refresh()
                elif kind == "snapshot":
                    self._apply_snapshot(payload)
                elif kind == "error":
                    self.status_var.set(str(payload))
        except queue.Empty:
            pass
        self.root.after(250, self._poll_queue)

    def _make_runtime_args(self) -> Namespace:
        return Namespace(
            symbol=self.args.symbol,
            timeframe=self.args.timeframe,
            bars=self.args.bars,
            terminal_path=self.args.terminal_path,
            calendar_path=self.args.calendar_path,
            outdir=self.args.outdir,
            symbol_timezone="UTC",
            loop=False,
            interval_minutes=self.args.interval_minutes,
            max_cycles=0,
            no_align=False,
        )

    def _schedule_immediate_refresh(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.root.after(150, self._begin_refresh)

    def _manual_refresh(self) -> None:
        self.next_refresh_at = None
        self.next_var.set("Manual refresh")
        self._schedule_immediate_refresh()

    def _begin_refresh(self) -> None:
        if self.running or self.bundles is None:
            return
        self.running = True
        self.status_var.set("Refreshing snapshot...")
        thread = threading.Thread(target=self._refresh_worker, daemon=True)
        thread.start()

    def _refresh_worker(self) -> None:
        try:
            snapshot = run_once(self._make_runtime_args(), self.bundles, self.outdir)
            self.snapshot_queue.put(("snapshot", snapshot))
        except Exception as exc:
            self.snapshot_queue.put(("error", f"Refresh failed: {exc}"))
            self.running = False

    def _apply_snapshot(self, snapshot: dict) -> None:
        self.running = False
        combined = snapshot["combined"]
        stage = snapshot["stage"]
        label = combined["regime_label"]

        self.stage_var.set(stage)
        self.label_var.set(label)
        self.high_vol_var.set(f"{combined['high_vol_prob']:.3f}")
        self.trend_var.set(f"{combined['trend_prob']:.3f}")
        self.regime_score_var.set(f"{combined['regime_score']:.3f}")
        self.generated_var.set(snapshot["generated_at_utc"])
        self.mode_var.set(self._build_mode_text(label, stage, combined["high_vol_prob"], combined["trend_prob"]))
        self._update_colors(label)
        self._fill_contribution_box(self.driver_text, snapshot["structural_model"]["top_contributions"])
        self._fill_contribution_box(self.event_text, snapshot["event_model"]["top_contributions"])
        self.status_var.set("Live window updated.")
        self._schedule_next_clock_run()

    def _schedule_next_clock_run(self) -> None:
        now = datetime.now()
        interval_seconds = max(60, int(self.args.interval_minutes * 60))
        elapsed = now.minute * 60 + now.second
        remainder = elapsed % interval_seconds
        wait_seconds = interval_seconds - remainder if remainder != 0 else interval_seconds
        self.next_refresh_at = now + timedelta(seconds=wait_seconds)
        self._tick_countdown()
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(wait_seconds * 1000, self._begin_refresh)

    def _tick_countdown(self) -> None:
        if self.countdown_job is not None:
            self.root.after_cancel(self.countdown_job)
            self.countdown_job = None
        if self.next_refresh_at is None:
            self.next_var.set("--")
            return
        remaining = self.next_refresh_at - datetime.now()
        total_seconds = max(0, int(remaining.total_seconds()))
        mm, ss = divmod(total_seconds, 60)
        self.next_var.set(f"{self.next_refresh_at.strftime('%H:%M:%S')} ({mm:02d}:{ss:02d})")
        self.countdown_job = self.root.after(1000, self._tick_countdown)

    def _fill_contribution_box(self, widget: Text | None, items: list[dict]) -> None:
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", END)
        for idx, item in enumerate(items, start=1):
            widget.insert(END, self._format_driver_explanation(idx, item))
        widget.configure(state="disabled")

    def _format_driver_explanation(self, idx: int, item: dict) -> str:
        feature = str(item["feature"])
        label = FEATURE_LABELS.get(feature, feature)
        meaning = FEATURE_MEANINGS.get(feature, "这是模型里的一个辅助状态因子，用来描述当前市场环境。")
        raw_value = float(item["raw_value"])
        standardized = float(item.get("standardized", 0.0))
        contribution = float(item["high_vol_contribution"])

        effect_text = "在推高高波动/扩张概率" if contribution >= 0 else "在压低高波动/扩张概率"
        strength = self._describe_strength(contribution)
        level = self._describe_level(standardized)
        feature_state = self._describe_feature_state(feature, raw_value, standardized)

        return (
            f"{idx}. {label}\n"
            f"   含义: {meaning}\n"
            f"   当前: {feature_state}，标准化位置{level}，原始值 {raw_value:.4f}\n"
            f"   作用: 这项目前{effect_text}，影响强度{strength}（贡献 {contribution:+.3f}）\n\n"
        )

    def _describe_strength(self, contribution: float) -> str:
        magnitude = abs(contribution)
        if magnitude >= 0.35:
            return "很强"
        if magnitude >= 0.15:
            return "中等"
        if magnitude >= 0.05:
            return "偏弱"
        return "很弱"

    def _describe_level(self, standardized: float) -> str:
        if standardized >= 1.0:
            return "明显偏高"
        if standardized >= 0.35:
            return "略偏高"
        if standardized <= -1.0:
            return "明显偏低"
        if standardized <= -0.35:
            return "略偏低"
        return "接近常态"

    def _describe_feature_state(self, feature: str, raw_value: float, standardized: float) -> str:
        if feature == "OPEN_OUTSIDE_PREV_RANGE":
            return "今天开盘已经跳出前日区间" if raw_value >= 0.5 else "今天开盘仍在前日区间内"
        if feature == "london2h_break_prevday":
            return "伦敦前两小时已经突破前日高低" if raw_value >= 0.5 else "伦敦前两小时还没有突破前日高低"
        if feature == "WEEKEND_GEO_CARRY":
            return "周末地缘冲击正在向今天传导" if raw_value >= 0.5 else "没有明显的周末地缘延续效应"
        if feature.endswith("_rows"):
            return "今天这类高影响事件存在感偏强" if raw_value > 0 else "今天这类事件基本缺席"
        if "geo" in feature.lower():
            return "地缘冲击偏强" if standardized > 0.35 else "地缘冲击不算强"
        if "dxy" in feature.lower():
            return "美元昨天波动偏大" if standardized > 0.35 else "美元昨天比较平静"
        if "vix" in feature.lower():
            return "恐慌波动昨天偏强" if standardized > 0.35 else "恐慌波动昨天不算强"
        if "tnx" in feature.lower():
            return "美债收益率昨天变动偏大" if standardized > 0.35 else "美债收益率昨天比较平稳"
        if "oil" in feature.lower():
            return "原油昨天波动偏大" if standardized > 0.35 else "原油昨天比较平静"
        if "gld" in feature.lower():
            return "GLD相关资金或波动偏活跃" if standardized > 0.35 else "GLD侧资金与波动偏平"
        if "gvz" in feature.lower():
            return "黄金隐波昨天偏强" if standardized > 0.35 else "黄金隐波昨天偏稳"
        if "gc_volume" in feature.lower():
            return "COMEX黄金期货昨天明显放量" if standardized > 0.35 else "COMEX黄金期货昨天未见明显放量"
        if "jpy" in feature.lower():
            return "日元避险流昨天有明显变化" if abs(standardized) > 0.35 else "日元避险流昨天变化不大"
        if "range_ratio" in feature.lower():
            return "波动幅度偏大" if standardized > 0.35 else "波动幅度偏小或接近常态"
        if "body_ratio" in feature.lower():
            return "K线实体偏强，更像方向推进" if standardized > 0.35 else "K线实体偏弱，更像来回拉扯"
        if "dist" in feature.lower():
            return "价格离前日关键位很近" if standardized < -0.35 else "价格离前日关键位不算近"
        return "该因子当前处在偏强状态" if standardized > 0.35 else "该因子当前没有明显异常"

    def _build_mode_text(self, label: str, stage: str, high_vol: float, trend: float) -> str:
        if label == "TREND_EXPANSION":
            return f"Mode: Trend day bias | high-vol {high_vol:.1%} | trend {trend:.1%} | stage {stage}"
        if label == "HIGH_VOLATILITY":
            return f"Mode: Expansion risk day | high-vol {high_vol:.1%} | trend {trend:.1%} | stage {stage}"
        if label == "TRANSITION":
            return f"Mode: Transition / mixed regime | high-vol {high_vol:.1%} | trend {trend:.1%} | stage {stage}"
        return f"Mode: Calm range bias | high-vol {high_vol:.1%} | trend {trend:.1%} | stage {stage}"

    def _update_colors(self, label: str) -> None:
        if self.header_label is None:
            return
        color_map = {
            "TREND_EXPANSION": ("#7b1e1e", "#fff3f1"),
            "HIGH_VOLATILITY": ("#8a4e00", "#fff7eb"),
            "TRANSITION": ("#5e4b00", "#fffbe8"),
            "CALM_RANGE": ("#215c3d", "#eef9f1"),
        }
        fg, bg = color_map.get(label, ("#6a4a1e", "#fffaf1"))
        self.header_label.configure(fg=fg, bg=bg)
        self.header_label.master.configure(bg=bg)
        for child in self.header_label.master.winfo_children():
            try:
                child.configure(bg=bg)
            except Exception:
                pass

    def _on_close(self) -> None:
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        if self.countdown_job is not None:
            self.root.after_cancel(self.countdown_job)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    args = parse_args()
    app = RegimeDashboard(args)
    app.run()


if __name__ == "__main__":
    main()
