# Doc 12 — Legal & Compliance Guide
## ASX Screener — Australian Stock Screener Platform

**Prepared:** April 2026  
**Jurisdiction:** Australia  
**Business Model:** SaaS subscription — stock data & screening tool (no financial advice)

---

## 1. What We Are Building

ASX Screener is a **data and analysis tool** that:
- Provides financial ratios, annual statements, balance sheets, cash flow data
- Allows users to create their own customised screening criteria
- Returns a list of stocks matching user-defined criteria
- Does **NOT** recommend any specific stock
- Does **NOT** provide personalised investment advice
- Empowers users to make their **own** informed decisions

This is the same model as **Screener.in** (India), **Stock Analysis** (USA), and **Macrotrends** (USA).

---

## 2. AFSL — Australian Financial Services Licence

### Do We Need One?

**Almost certainly NO** — based on the following distinction:

| Activity | AFSL Required? |
|----------|---------------|
| "Buy BHP, it will go up 20%" | ✅ Yes — financial product advice |
| "Here are 50 stocks with PE < 15 and ROE > 20%" | ❌ No — factual data/screening tool |
| Showing balance sheets, ratios, cash flows | ❌ No — factual information |
| Personalised portfolio recommendations | ✅ Yes |
| User-defined filter tool returning matching stocks | ❌ No |
| AI insights summarising annual reports | ❌ No (factual summary) |

### Why We Are Safe Without an AFSL

Under the **Corporations Act 2001 (Cth)**, an AFSL is required only when a person:
- Provides **financial product advice** (a recommendation to acquire/dispose of a financial product), OR
- **Deals** in financial products (buys/sells on behalf of clients)

ASX Screener does neither. We provide:
- **Factual information** — financial statements, ratios, historical data
- **A tool** — users apply their own criteria and make their own decisions

### Comparison with Simply Wall St

Simply Wall St (Australian company, AFSL 469216) obtained an AFSL because their "Snowflake" scoring system and stock "health" scores could be construed as implicit recommendations. **We avoid this risk** by:
- Never scoring stocks as "good" or "bad"
- Never ranking stocks by investment merit
- Letting users define all criteria themselves

### Recommended Action

- [ ] Engage an Australian fintech lawyer for a one-time compliance review (~$1,000–$1,500)
- [ ] Confirm AFSL exemption in writing before commercial launch
- [ ] Review annually as product features evolve

---

## 3. Data Licensing — CRITICAL

### The Yahoo Finance Problem ⚠️

We currently use Yahoo Finance for price data. **This violates Yahoo's Terms of Service for commercial use.**

Yahoo Finance Terms of Service state:
> "You may not use, distribute, publish, or replicate any data for commercial purposes without express written permission."

**Risk:** Cease and desist, data cutoff, legal liability.

### Solution — Switch to FMP (Financial Modeling Prep)

| Provider | Commercial Use | ASX Coverage | Cost | What It Covers |
|----------|---------------|--------------|------|----------------|
| **Yahoo Finance** | ❌ Not allowed | ✅ Good | Free | Price data only |
| **FMP** ✅ Recommended | ✅ Licensed | ✅ Full | $15–$79/mo | Prices + Financials |
| **Refinitiv/LSEG** | ✅ Licensed | ✅ Full | $500+/mo | Enterprise grade |
| **ASX Direct** | ✅ Licensed | ✅ Full | $1,000+/mo | Real-time ASX data |
| **Alpha Vantage** | ✅ Paid plans | ✅ Good | $50+/mo | Prices + some financials |

### FMP Plan Recommendation

| Plan | Price | API Calls/day | Suitable For |
|------|-------|--------------|--------------|
| Starter | $15/mo | Unlimited | Dev/early launch |
| Professional | $79/mo | Unlimited + bulk | Growth stage |
| Enterprise | Custom | Unlimited | Scale |

**FMP provides:**
- ✅ Daily/historical price data for all ASX stocks
- ✅ Annual income statements (10+ years)
- ✅ Annual balance sheets (10+ years)
- ✅ Annual cash flow statements (10+ years)
- ✅ Half-yearly/quarterly reports
- ✅ Dividend history
- ✅ Key financial ratios
- ✅ Commercial licence included

**Action Required Before Commercial Launch:**
- [ ] Sign up for FMP API at financialmodelingprep.com
- [ ] Replace Yahoo Finance price loader with FMP price loader
- [ ] Build FMP financial data loader (replaces manual financial data entry)
- [ ] Store API key securely in `.env` / server environment

---

## 4. Other Regulatory Bodies

| Body | What They Regulate | Our Obligation |
|------|-------------------|----------------|
| **ASIC** | Financial services, company registration | No AFSL needed; register business name (~$39/yr) |
| **AUSTRAC** | Anti-money laundering, payments | Stripe handles all payment compliance for us |
| **ATO** | Tax, GST | Register for GST when revenue exceeds $75,000/yr |
| **OAIC** | Privacy, data protection | Write and publish a Privacy Policy |
| **ACCC** | Consumer law, fair trading | Clear Terms of Service, refund policy |
| **ASX** | Market data licensing | Use FMP instead of direct ASX real-time feed |

---

## 5. Mandatory Legal Documents

### 5.1 Privacy Policy

Required under the **Privacy Act 1988 (Cth)** and **Australian Privacy Principles (APPs)**.

Must cover:
- What personal information we collect (email, name, payment details)
- How we collect it (sign-up form, Stripe payment)
- How we use it (account management, billing, alerts)
- How we store and protect it (encrypted database, SSL)
- Whether we share it (no — except Stripe for payments)
- How users can access/correct their data
- How to contact us about privacy concerns
- Cookie usage and analytics
- GDPR compliance for EU/UK users

### 5.2 Terms of Service

Must cover:
- Service description (data tool, not financial advice)
- User eligibility (18+, must agree to not rely on data as advice)
- Subscription plans and pricing
- Payment terms (auto-renewal, billing cycle)
- Cancellation and refund policy (Australian Consumer Law requires fair policy)
- Intellectual property (we own the platform; FMP/ASX own underlying data)
- Limitation of liability (data accuracy disclaimer)
- Dispute resolution

### 5.3 Financial Disclaimer (on every page)

```
IMPORTANT DISCLAIMER: ASX Screener provides financial data and 
screening tools for informational purposes only. Nothing on this 
website constitutes financial product advice, a recommendation to 
buy or sell any security, or a solicitation of any investment 
decision. Past performance is not indicative of future results. 
You should consider seeking independent financial advice from a 
licensed financial adviser before making any investment decision. 
ASX Screener Pty Ltd does not hold an Australian Financial Services 
Licence (AFSL).
```

### 5.4 Cookie Policy

Required for EU/UK visitors under GDPR/UK GDPR:
- List all cookies used (analytics, session, preferences)
- Allow users to accept/reject non-essential cookies
- Implement a cookie consent banner

---

## 6. Business Registration Checklist

### Before Launch

- [ ] **ABN Registration** — Free at abr.gov.au (5 minutes)
- [ ] **Business Name** — Register "ASX Screener" at ASIC Connect (~$39/yr for 1 year, $92/3 years)
- [ ] **Company Structure** — Consider Pty Ltd for liability protection (~$538 ASIC fee + legal fees)
- [ ] **Business Bank Account** — Separate from personal finances
- [ ] **Accounting Software** — Xero or QuickBooks for GST reporting

### At $75,000+ Annual Revenue

- [ ] **GST Registration** — Register with ATO, add 10% GST to Australian customers
- [ ] **BAS Lodgement** — Quarterly Business Activity Statements
- [ ] **Tax Advice** — Engage an accountant

---

## 7. Subscription & Payment Compliance

### Australian Consumer Law Requirements

Under the **Australian Consumer Law (ACL)**:
- Clearly display all pricing (including GST when applicable)
- Clearly state what's included in each plan
- Provide a fair cancellation policy
- No hidden fees or auto-renewal without prior disclosure

### Recommended Subscription Terms

```
Free Plan:    No credit card required. No expiry.
Pro Plan:     $X/month or $X/year. Auto-renews. Cancel anytime.
              Cancellation takes effect at end of billing period.
              No refunds for partial periods (state this clearly).
Premium Plan: Same terms as Pro.
```

### Stripe (Payment Processor)

Stripe handles:
- ✅ PCI DSS compliance (credit card security)
- ✅ AUSTRAC registration (they are a registered financial institution)
- ✅ Fraud detection
- ✅ Automatic GST calculation (configurable)
- ✅ Subscription management and invoicing

We are responsible for:
- Providing correct GST rates to Stripe
- Issuing tax invoices to customers (Stripe does this automatically)
- Reporting GST to ATO quarterly

---

## 8. Data Accuracy & Liability

### Key Risk

Financial data can have errors. If a user makes an investment decision based on incorrect data we display, we could face liability.

### Mitigation

1. **Disclaimer on every page** (see 5.3 above)
2. **Terms of Service** — limit liability to subscription fees paid
3. **Data source attribution** — display "Data provided by Financial Modeling Prep"
4. **No guarantee of accuracy** — state clearly data may have errors/delays
5. **Encourage verification** — "Always verify data with official ASX announcements"

---

## 9. Competitor Reference — How Similar Platforms Handle This

| Platform | Country | AFSL | Data Source | Disclaimer |
|----------|---------|------|-------------|-----------|
| Screener.in | India | No | BSE/NSE licensed | "Not financial advice" |
| Simply Wall St | Australia | Yes (469216) | Proprietary | Full AFSL disclosure |
| Stock Analysis | USA | No | FMP + others | "Not financial advice" |
| Macrotrends | USA | No | FRED + others | "Not investment advice" |
| Wisesheets | Canada | No | FMP | "Educational purposes" |
| **ASX Screener** | Australia | No (target) | FMP (target) | "Not financial advice" |

---

## 10. Recommended Timeline

| Milestone | Action | Timeline |
|-----------|--------|----------|
| **Now** | Sign up for FMP API | This week |
| **Now** | Replace Yahoo Finance with FMP | This sprint |
| **Pre-launch** | Engage fintech lawyer | 4 weeks before launch |
| **Pre-launch** | Write Privacy Policy + ToS | 4 weeks before launch |
| **Pre-launch** | Register ABN + business name | 2 weeks before launch |
| **Pre-launch** | Add disclaimer footer to all pages | 1 week before launch |
| **Launch** | Enable Stripe subscriptions | Launch day |
| **Post-launch** | Review GST obligations | Monthly |
| **$75K revenue** | Register for GST | When threshold hit |
| **Annual** | Legal compliance review | Every 12 months |

---

## 11. Summary — Are We Legal?

| Question | Answer |
|----------|--------|
| Do we need an AFSL? | Almost certainly No — pure data tool |
| Can we charge subscriptions? | Yes — SaaS subscription model is fine |
| Can we use Yahoo Finance data commercially? | No — must switch to FMP |
| Do we need ASIC approval? | No — but register business name with ASIC |
| Do we need AUSTRAC registration? | No — Stripe handles payments |
| Do we need a Privacy Policy? | Yes — mandatory under Privacy Act 1988 |
| Do we need Terms of Service? | Yes — mandatory for paid service |
| Do we need GST registration? | Not until $75K/yr revenue |

**Bottom Line:** ASX Screener is legally buildable and commercially viable without an AFSL. The main action items are switching from Yahoo Finance to FMP, writing proper legal documents, and registering the business.

---

*This document is for internal planning purposes only and does not constitute legal advice. Consult a qualified Australian fintech lawyer before commercial launch.*
