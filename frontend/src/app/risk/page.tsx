import type { Metadata } from "next";
import { DocList, DocSection, DocShell, DocTable } from "@/components/marketing/doc-shell";

export const metadata: Metadata = {
  title: "Trading risk policy",
  description:
    "The deterministic limits VELTRANE enforces on every order, the kill switches, and the authorisation required before any live trade.",
};

const CHECKS: string[][] = [
  ["kill_switch", "Global, tenant, provider or user switch engaged", "engaged = reject"],
  ["mode_authorization", "Live requested without entitlement or platform flag", "off = reject live"],
  ["circuit_breaker", "Four consecutive losses hold new entries for 60 minutes", "exits still allowed"],
  ["market_data", "Quote exists and is fresher than the window", "30 seconds"],
  ["order_validation", "Quantity, price band, minimum notional, limit sanity", "10 notional, 5% band"],
  ["position_size", "Resulting position against account equity", "10% of equity"],
  ["exposure", "Account and portfolio exposure, leverage", "30% / 50% / 3x"],
  ["max_open_positions", "Count of open positions", "5"],
  ["stop_loss", "Live entries must carry a stop inside the allowed band", "required, max 12%"],
  ["duplicate_order", "Identical contract inside the window", "60 seconds"],
  ["daily_loss_limit", "Loss for the UTC day", "3% of equity"],
  ["drawdown_limit", "Peak-to-trough on the account", "15%"],
  ["demo_execution_limit", "Simulated executions per day", "5 / day on Free"],
];

const AUTHORISATION = [
  "A plan that includes live trading. Pro, Elite and VIP by default; configurable by the operator.",
  "A connected account with a verified read-only synchronisation.",
  "A recorded acknowledgement of this risk document, at its current version.",
  "All eight safety checklist items accepted individually.",
  "MFA verified in the session, or a written waiver recorded for accounts that cannot use TOTP.",
  "A confirmation token issued at the end of the checklist and used within 60 seconds.",
  "The live trading flag enabled at the process level by the operator.",
];

export default function RiskPolicyPage() {
  return (
    <DocShell
      eyebrow="Risk"
      title="Trading risk policy"
      summary="This is the policy the software enforces, not a description of intent. Every order, simulated or live, is evaluated by a deterministic engine that the strategy layer cannot influence, and every rejection is stored with the reason it failed."
      version="risk-disclosure-2026-01"
    >
      <DocSection title="The engine sits between intent and execution">
        <p>
          A strategy produces an order request. It has no write access to orders and cannot change a
          limit. The risk engine is pure: the same inputs always produce the same decision, and no
          model is consulted. Execution is the only component that talks to a venue, and it re-checks
          the platform flag and the kill switches immediately before doing so.
        </p>
        <p>
          There is no override path in the code. An operator cannot push a failed order through, and
          an AI suggestion cannot bypass a check.
        </p>
      </DocSection>

      <DocSection title="Checks applied to every order">
        <DocTable head={["Rule", "What it measures", "Default"]} rows={CHECKS} />
        <p className="text-2xs text-paper-faint">
          Defaults ship with the software. Operators can change them, and every change creates a new
          policy version; each order records the version that evaluated it.
        </p>
      </DocSection>

      <DocSection title="Results are net of costs">
        <DocList
          items={[
            "Simulated fills apply taker fee, half-spread and slippage against the trade direction. The estimate and the realised figure are stored separately per trade.",
            "Backtests subtract the same fee, spread and slippage per side, plus funding accrual for perpetual instruments.",
            "Portfolio performance is reported after recorded fees and funding. Gross figures are never the headline.",
            "Funding and borrow costs are modelled per trade rather than assumed to be zero.",
          ]}
        />
      </DocSection>

      <DocSection title="Kill switches">
        <p>
          Switches exist at four scopes: the whole platform, one tenant, one provider, or one user.
          Engaging one writes an audited record with the actor, reason and timestamp, mirrors the
          state so background workers see it without a database round trip, and blocks every
          subsequent order at that scope. Release requires the same role as engagement.
        </p>
        <p>
          The global control is reachable from the admin console, from the API, and from a file flag,
          so it still works when the application is not open.
        </p>
      </DocSection>

      <DocSection title="What live trading requires">
        <p>All of the following, in this order. A subscription alone authorises nothing.</p>
        <DocList items={AUTHORISATION} />
        <p>Revoking authorisation is immediate and needs no confirmation.</p>
      </DocSection>

      <DocSection title="What the platform will not do">
        <DocList
          items={[
            "Claim, imply or display a guaranteed return.",
            "Optimise for trade frequency or gross profit.",
            "Present simulated results as real results. Demo payloads are flagged and labelled in the interface.",
            "Submit an order that failed a risk check, for any reason.",
            "Enable live trading as a side effect of a subscription purchase or an onboarding step.",
          ]}
        />
      </DocSection>

      <DocSection title="Your capital is at risk">
        <p>
          Trading leveraged products can lose money faster than it makes it. Past performance,
          including simulated performance, does not indicate future results. VELTRANE does not hold
          client funds and cannot move money out of your brokerage account, because withdrawal
          permission is prohibited by product design and by the connection checklist.
        </p>
      </DocSection>
    </DocShell>
  );
}
