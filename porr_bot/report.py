"""Daily P&L email: today's trades, plus week-to-date and month-to-date P&L, read from trades.csv.

Email is sent with SMTP (e.g. Gmail with an App Password). Settings in config.toml [email];
the password comes from the SMTP_PASSWORD environment variable, never from the config file.
"""
from __future__ import annotations

import csv
import logging
import os
import smtplib
from datetime import date, datetime, timedelta
from email.message import EmailMessage

log = logging.getLogger("porr.report")


def trade_net(row: dict, tick_value: float, comm_per_side: float) -> float:
    qty = int(float(row["qty"]))
    return float(row["pnl_ticks"]) * tick_value * qty - 2 * comm_per_side * qty


def load_trades(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def summarize(trades: list[dict], day: date, tick_value: float = 0.5, comm_per_side: float = 0.7) -> dict:
    """Net P&L for `day`, the week (Mon..day) and the month (1st..day) - by trade ENTRY date."""
    week_start = day - timedelta(days=day.weekday())
    month_start = day.replace(day=1)
    out = {"day": [], "week": 0.0, "month": 0.0, "week_n": 0, "month_n": 0}
    for r in trades:
        d = datetime.fromisoformat(str(r["entry_time"])).date()
        net = trade_net(r, tick_value, comm_per_side)
        if d == day:
            out["day"].append((r, net))
        if week_start <= d <= day:
            out["week"] += net; out["week_n"] += 1
        if month_start <= d <= day:
            out["month"] += net; out["month_n"] += 1
    out["today"] = sum(n for _, n in out["day"])
    return out


def build_message(s: dict, day: date, mode: str, regime: str | None = None) -> tuple[str, str]:
    m = lambda v: ("+" if v >= 0 else "-") + f"${abs(v):,.2f}"
    subject = f"PORR {mode} {day.isoformat()}: today {m(s['today'])} | week {m(s['week'])} | month {m(s['month'])}"
    lines = [f"PORR bot ({mode}) - {day.strftime('%A %Y-%m-%d')}", ""]
    if regime:
        lines += [f"Day type: {regime}", ""]
    lines += [f"Today:          {m(s['today'])}  ({len(s['day'])} trade{'s' if len(s['day']) != 1 else ''})",
              f"Week to date:   {m(s['week'])}  ({s['week_n']} trades)",
              f"Month to date:  {m(s['month'])}  ({s['month_n']} trades)", ""]
    if s["day"]:
        lines.append("Today's trades:")
        for r, net in s["day"]:
            side = "Long" if int(float(r["dir"])) > 0 else "Short"
            t_in = str(r["entry_time"])[11:19]; t_out = str(r["exit_time"])[11:19]
            lines.append(f"  {r['tag']:<9} {side:<5} {r['qty']} @ {r['entry']} -> {r['exit']} ({r['exit_type']})  "
                         f"{t_in}-{t_out}  {float(r['pnl_ticks']):+.0f} ticks  {m(net)}")
    else:
        lines.append("No trades today.")
    lines += ["", "Net of commission; simulated fills in paper mode."]
    return subject, "\n".join(lines)


def send_email(cfg: dict, subject: str, body: str) -> None:
    """cfg: [email] section. Password from env SMTP_PASSWORD."""
    pw = os.environ.get("SMTP_PASSWORD")
    if not pw:
        raise RuntimeError("SMTP_PASSWORD environment variable is not set")
    msg = EmailMessage()
    msg["Subject"] = subject; msg["From"] = cfg["from"]; msg["To"] = cfg["to"]
    msg.set_content(body)
    with smtplib.SMTP(cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 587)), timeout=30) as s:
        s.starttls(); s.login(cfg.get("username", cfg["from"]), pw); s.send_message(msg)
    log.info("P&L email sent to %s", cfg["to"])


def daily_report(trade_log: str, email_cfg: dict, day: date, mode: str, regime: str | None = None,
                 tick_value: float = 0.5, comm_per_side: float = 0.7) -> str:
    s = summarize(load_trades(trade_log), day, tick_value, comm_per_side)
    subject, body = build_message(s, day, mode, regime)
    log.info("%s\n%s", subject, body)
    if email_cfg.get("enabled"):
        try:
            send_email(email_cfg, subject, body)
        except Exception:
            log.exception("could not send the P&L email")
    return body
