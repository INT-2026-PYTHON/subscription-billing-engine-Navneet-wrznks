"""
CLI entrypoint.

Subcommands to implement (Day 4):
    billing init                              -- create / migrate the DB
    billing customer add <name> <email> <country> [--state CODE]
    billing plan list
    billing subscribe <customer_id> <plan_id> [--trial-days N] [--discount CODE]
    billing bill run [--date YYYY-MM-DD]
    billing invoice show <invoice_id>          -- prints PLAIN TEXT invoice
    billing upgrade <subscription_id> <new_plan_id> [--date YYYY-MM-DD]   (STRETCH)
    billing demo                              -- run the scripted scenario

Use argparse with subparsers. Keep each subcommand handler in its own function.

PDF rendering is OUT OF SCOPE for the core project — `invoice show` should
print a clean PLAIN-TEXT invoice (see helper `format_invoice_text` below).
PDF generation is BONUS: see `billing_engine/pdf/renderer.py`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from billing_engine.models import Invoice


def format_invoice_text(invoice: Invoice, customer_name: str, plan_name: str) -> str:
    """Render an invoice as a plain-text receipt. Pure function — easy to test."""
    W    = 60
    DIV  = "=" * W
    THIN = "-" * W
    ccy  = invoice.currency

    lines = [
         DIV,
         f"{'INVOICE INV-' + str(invoice.id):^{W}}",
         DIV,
         f"Customer: {customer_name}",
         f"Period:   {invoice.period_start} → {invoice.period_end}",
         f"Status:   {invoice.status.value}",
         THIN,
    ]     
    
    for item in invoice.line_items:
        label  = item.description or item.kind.value
        amount = item.amount.rounded().amount
        sign   = "-" if amount < 0 else " "
        lines.append(f"{label:<44}  {ccy} {sign}{abs(amount):>8.2f}")


    lines += [
         THIN,
         f"{'Subtotal:':<44}  {ccy}  {invoice.subtotal.rounded().amount:>8.2f}",
         f"{'Discount:':<44}  {ccy}  {invoice.discount_total.rounded().amount:>8.2f}",
         f"{'Tax:':<44}  {ccy}  {invoice.tax_total.rounded().amount:>8.2f}",
         THIN,
         f"{'TOTAL:':<44}  {ccy}  {invoice.total.rounded().amount:>8.2f}",
         DIV,
    ]

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from billing_engine.db.database import Database
    from billing_engine.db.repository import (
        CustomerRepository, PlanRepository, SubscriptionRepository,
        UsageRecordRepository, InvoiceRepository, InvoiceLineItemRepository,
        LedgerRepository, PaymentAttemptRepository,
    )
    from billing_engine.models import (
        Customer, Subscription, SubscriptionStatus,
    )
    from billing_engine.billing.cycle import BillingCycle
    from billing_engine.pricing import FlatRate
    from billing_engine.taxes import NoTax, TaxContext
    from billing_engine.money import Money
    import json

    DB_PATH = "billing.db"
    parser = argparse.ArgumentParser(prog="billing", description="Subscription Billing CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="initialize the database")

    # customer add
    cust_p = sub.add_parser("customer")
    cust_s = cust_p.add_subparsers(dest="customer_subcmd", required=True)
    add_p  = cust_s.add_parser("add")
    add_p.add_argument("name")
    add_p.add_argument("email")
    add_p.add_argument("country_code", metavar="COUNTRY")
    add_p.add_argument("--state", dest="state_code", default="")

    # plan list
    plan_p = sub.add_parser("plan")
    plan_s = plan_p.add_subparsers(dest="plan_subcmd", required=True)
    plan_s.add_parser("list")

    # subscribe
    sub_p = sub.add_parser("subscribe")
    sub_p.add_argument("customer_id",  type=int)
    sub_p.add_argument("plan_id",      type=int)
    sub_p.add_argument("--trial-days",  type=int, default=0,    dest="trial_days")
    sub_p.add_argument("--discount-id", type=int, default=None, dest="discount_id")

    # bill run
    bill_p = sub.add_parser("bill")
    bill_s = bill_p.add_subparsers(dest="bill_subcmd", required=True)
    run_p  = bill_s.add_parser("run")
    run_p.add_argument("--date", default=None, metavar="YYYY-MM-DD")

    # invoice show
    inv_p  = sub.add_parser("invoice")
    inv_s  = inv_p.add_subparsers(dest="invoice_subcmd", required=True)
    show_p = inv_s.add_parser("show")
    show_p.add_argument("invoice_id", type=int)

    # upgrade
    up_p = sub.add_parser("upgrade")
    up_p.add_argument("subscription_id", type=int)
    up_p.add_argument("new_plan_id",      type=int)
    up_p.add_argument("--date", default=None, metavar="YYYY-MM-DD")

    sub.add_parser("demo", help="run the demo scenario")

    args = parser.parse_args(argv)

    if args.cmd == "init":
        db = Database(DB_PATH)
        db.init_schema()
        print(f"✓ Database initialised at {DB_PATH}")
        return 0

    if args.cmd == "demo":
        return run_demo()

    db        = Database(DB_PATH)
    cust_repo = CustomerRepository(db)
    plan_repo = PlanRepository(db)
    sub_repo  = SubscriptionRepository(db)
    inv_repo  = InvoiceRepository(db)
    li_repo   = InvoiceLineItemRepository(db)

    def _make_cycle():
        def _sf(plan):
            try:
                price = json.loads(plan.config_json or "{}").get("price", "0")
            except Exception:
                price = "0"
            return FlatRate(Money(price, plan.currency))
        return BillingCycle(
            db=db,
            customer_repo=cust_repo, plan_repo=plan_repo,
            subscription_repo=sub_repo,
            usage_repo=UsageRecordRepository(db),
            invoice_repo=inv_repo, line_item_repo=li_repo,
            ledger_repo=LedgerRepository(db),
            strategy_factory=_sf,
            discount_factory=lambda _: None,
            tax_factory=lambda c: (NoTax(), TaxContext(customer_country=c.country_code)),
        )

    if args.cmd == "customer" and args.customer_subcmd == "add":
        cust = cust_repo.add(Customer(
            None, args.name, args.email, args.country_code, args.state_code,
        ))
        print(f"✓ Customer  id={cust.id}  {cust.name} <{cust.email}>")

    elif args.cmd == "plan" and args.plan_subcmd == "list":
        plans = plan_repo.list_all()
        if not plans:
            print("No plans found.")
        else:
            print(f"{'ID':<5} {'Name':<20} {'Type':<10} {'Period':<10} {'CCY'}")
            print("-" * 52)
            for p in plans:
                print(f"{p.id:<5} {p.name:<20} "
                      f"{p.pricing_type.value:<10} {p.billing_period.value:<10} {p.currency}")

    elif args.cmd == "subscribe":
        today      = date.today()
        trial_days = args.trial_days or 0
        trial_end  = (today + timedelta(days=trial_days)) if trial_days else None
        status     = SubscriptionStatus.TRIAL if trial_end else SubscriptionStatus.ACTIVE
        period_end = (trial_end + timedelta(days=30)) if trial_end else (today + timedelta(days=30))
        s = sub_repo.add(Subscription(
            None, args.customer_id, args.plan_id, status,
            today, period_end, trial_end, args.discount_id,
        ))
        print(f"✓ Subscription  id={s.id}  customer={s.customer_id}  "
              f"plan={s.plan_id}  status={s.status.value}")

    elif args.cmd == "bill" and args.bill_subcmd == "run":
        run_date = date.fromisoformat(args.date) if args.date else date.today()
        r = _make_cycle().run(as_of=run_date)
        print(f"✓ Billing run {run_date}: {r.invoices_created} created  "
              f"{r.invoices_skipped_duplicate} skipped  "
              f"{r.trials_activated} trials activated")

    elif args.cmd == "invoice" and args.invoice_subcmd == "show":
        inv = inv_repo.get(args.invoice_id)
        if inv is None:
            print(f"Invoice {args.invoice_id} not found.", file=sys.stderr)
            return 1
        s    = sub_repo.get(inv.subscription_id)
        cust = cust_repo.get(s.customer_id)
        plan = plan_repo.get(s.plan_id)
        inv.line_items[:] = li_repo.list_for_invoice(inv.id)
        print(format_invoice_text(inv, cust.name, plan.name))

    elif args.cmd == "upgrade":
        upgrade_date = date.fromisoformat(args.date) if args.date else date.today()
        pr_inv = _make_cycle().upgrade_subscription(
            subscription_id=args.subscription_id,
            new_plan_id=args.new_plan_id,
            switch_date=upgrade_date,
        )
        s    = sub_repo.get(args.subscription_id)
        cust = cust_repo.get(s.customer_id)
        plan = plan_repo.get(args.new_plan_id)
        pr_inv.line_items[:] = li_repo.list_for_invoice(pr_inv.id)
        print(f"✓ Upgraded subscription {args.subscription_id} → plan {args.new_plan_id}")
        print(format_invoice_text(pr_inv, cust.name, plan.name))

    return 0


def run_demo() -> int:
    """Scripted end-to-end scenario for the `demo` subcommand.

    Should mirror `tests/test_demo_scenario.py::TestEndToEndScenario::test_full_lifecycle`
    and print a human-readable summary to stdout.
    """
    import tempfile, os
    from pathlib import Path
    from billing_engine.db.database import Database
    from billing_engine.db.repository import (
        CustomerRepository, PlanRepository, SubscriptionRepository,
        UsageRecordRepository, InvoiceRepository, InvoiceLineItemRepository,
        LedgerRepository, PaymentAttemptRepository,
    )
    from billing_engine.models import (
        Customer, Plan, PricingType, BillingPeriod,
        Subscription, SubscriptionStatus, LedgerDirection,
    )
    from billing_engine.money import Money
    from billing_engine.billing.cycle import BillingCycle
    from billing_engine.billing.dunning import DunningProcess, DunningState
    from billing_engine.payments.gateway import ScriptedGateway, PaymentResult
    from billing_engine.pricing import FlatRate
    from billing_engine.taxes import NoTax, TaxContext
    from datetime import date, datetime, timedelta

    PRICES = {
        "Starter": Money("900",  "INR"),
        "Pro":     Money("2900", "INR"),
    }

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        db = Database(path)
        db.init_schema()

        cust_repo  = CustomerRepository(db)
        plan_repo  = PlanRepository(db)
        sub_repo   = SubscriptionRepository(db)
        inv_repo   = InvoiceRepository(db)
        li_repo    = InvoiceLineItemRepository(db)
        ledger_repo = LedgerRepository(db)
        att_repo   = PaymentAttemptRepository(db)

        def _make_cycle():
            return BillingCycle(
                db=db,
                customer_repo=cust_repo, plan_repo=plan_repo,
                subscription_repo=sub_repo,
                usage_repo=UsageRecordRepository(db),
                invoice_repo=inv_repo, line_item_repo=li_repo,
                ledger_repo=ledger_repo,
                strategy_factory=lambda p: FlatRate(PRICES[p.name]),
                discount_factory=lambda _: None,
                tax_factory=lambda c: (NoTax(), TaxContext(customer_country=c.country_code)),
            )
        
        #Step 1: seed
        starter = plan_repo.add(Plan(None, "Starter", PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
        pro     = plan_repo.add(Plan(None, "Pro",     PricingType.FLAT, BillingPeriod.MONTHLY, "INR"))
        alice   = cust_repo.add(Customer(None, "Alice", "alice@example.com", "AE"))
        sub     = sub_repo.add(Subscription(
            None, alice.id, starter.id, SubscriptionStatus.ACTIVE,
            date(2026, 1, 1), date(2026, 2, 1),
        ))
        print(f"[Step 1] Customer id={alice.id}  Subscription id={sub.id}  plan=Starter")

         #Step 2: billing cycle 
        r = _make_cycle().run(as_of=date(2026, 2, 1))
        print(f"\n[Step 2] Billing cycle: {r.invoices_created} invoice(s) created")
        with db.connect() as conn:
            row = conn.execute(
                "SELECT id FROM invoices WHERE subscription_id=? ORDER BY id DESC LIMIT 1",
                (sub.id,)
            ).fetchone()
        inv = inv_repo.get(row["id"])
        inv.line_items[:] = li_repo.list_for_invoice(inv.id)
        print(format_invoice_text(inv, alice.name, starter.name))

         #Step 3: dunning
        print("\n[Step 3] Payment attempts")
        now      = datetime(2026, 2, 1, 10, 0)
        attempts = [
            (False, "INSUFFICIENT_FUNDS"),
            (False, "CARD_DECLINED"),
            (True,  None),
        ]
        labels = {
            DunningState.SUCCEEDED:    "SUCCESS ✓",
            DunningState.RETRYING:     "RETRYING",
            DunningState.FAILED_FINAL: "FAILED FINAL",
        }
        for success, reason in attempts:
            dunning = DunningProcess(
                gateway=ScriptedGateway([PaymentResult(success, reason)]),
                invoice_repo=inv_repo, ledger_repo=ledger_repo,
                subscription_repo=sub_repo, attempt_repo=att_repo,
            )
            o = dunning.attempt(inv_repo.get(inv.id), alice.id, now)
            retry = f"  → retry at {o.next_retry_at}" if o.next_retry_at else ""
            print(f"  {labels.get(o.state, str(o.state))}{retry}")
            now += timedelta(days=3)

         # ── Step 4: upgrade ───────────────────────────────────────────────────
        print("\n[Step 4] Mid-cycle upgrade: Starter → Pro on 2026-02-15")
        pr_inv = _make_cycle().upgrade_subscription(sub.id, pro.id, date(2026, 2, 15))
        pr_inv.line_items[:] = li_repo.list_for_invoice(pr_inv.id)
        print(format_invoice_text(pr_inv, alice.name, pro.name))

         # ── Step 5: ledger ────────────────────────────────────────────────────
        print("\n[Step 5] Final ledger")
        W    = 60
        DIV  = "=" * W
        THIN = "-" * W
        print(DIV)
        print(f"  {'#':<4} {'Direction':<8} {'Amount':>16}  Reason")
        print(THIN)
        for i, e in enumerate(ledger_repo.list_for_customer(alice.id), 1):
            d    = e.direction.value
            sign = "+" if d == "CREDIT" else "-"
            print(f"  {i:<4} {d:<8} {sign}{str(e.amount):>15}  {e.reason}")
        print(DIV)

        print("\n✓ Demo complete")

    finally:
         db.close()
         import gc
         import time
         time.sleep(0.1)
         try:
             Path(path).unlink(missing_ok=True)
         except PermissionError:
             pass
             

    return 0


if __name__ == "__main__":
    raise SystemExit(main())