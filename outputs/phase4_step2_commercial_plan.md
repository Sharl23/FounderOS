# Commercial plan (ASSUMPTIONS, calculated in code)

- Price 5.0 USD/month; fee 0.45; contribution 4.06 (81.1%)
- Break-even: 5 sale(s) per month cover the fixed costs.

| Scenario | Sales/month | Profit/month | Months to recover build |
|---|---|---|---|
| low | 2 | -11.89 | never |
| base | 10 | 20.55 | 10 |
| high | 30 | 101.65 | 2 |

Payment provider: **MOCKED**: No payment provider is configured. Live payment processing is disabled in code; only the built-in TEST MODE simulator exists.

## Terms checklist
- [TO DO] Terms of service (draft): What the buyer gets, access period, acceptable use.
- [TO DO] Refund policy (draft): Must meet consumer rules in Egypt; check with a qualified professional.
- [TO DO] Privacy notice: What personal data is collected (FounderOS collects none in the prototype).
- [TO DO] Business registration and tax: Requirements in Egypt are not checked by FounderOS.
- [NOT CREATED] Payment provider account: FounderOS never creates accounts. Checkout is MOCKED / TEST MODE.

## Commercial recommendation: COLLECT PRICE EVIDENCE before relying on this plan

- **PRICE_UNSUPPORTED** (MEDIUM): No evidence is recorded for the price of 5.0 USD; it is an ASSUMPTION. Run the no-payment price-commitment test (Validate, claim C-VIAB) before treating this price as real.
- **BUDGET_NOT_COMPARABLE** (INFO): Your budget is in EGP and this plan is in USD; FounderOS does not convert currencies. Re-enter the plan in EGP to check affordability.
- **CHURN_SENSITIVITY** (INFO): Recurring revenue depends on churn: churn 5% -> about 20.0 months, 81.1 USD per customer; churn 10% -> about 10.0 months, 40.55 USD per customer; churn 20% -> about 5.0 months, 20.28 USD per customer. Churn is an ASSUMPTION until you observe real renewals; compare with a one-time price of about one lifetime contribution.

Missing inputs: evidence for the price

CALCULATED from ASSUMPTION inputs. Not a profit forecast; not financial, tax or legal advice.
