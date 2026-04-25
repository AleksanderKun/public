# Polish Crypto Taxation Guide (PIT-38) - Technical & Legal Reference

## Polish Tax Law Framework (2026)

This document explains the Polish tax law principles implemented in this module.

### 1. Taxable Event Definition

Per Polish tax authority (KIS), a **taxable event** occurs when:

#### **TAXABLE EVENTS** (Must report to tax authority)

1. **Sale of Crypto for Fiat**
   - Selling BTC/ETH/ALT for PLN, USD, EUR, etc.
   - Event: Fiat is received
   - Tax basis: Fiat amount converted to PLN using NBP rate (T-1)
   - Example: Sell 1 BTC for 5,000 USD → Convert USD to PLN → Report as revenue

2. **Using Crypto to Pay for Goods/Services**
   - Spending crypto to purchase real-world items
   - Event: Crypto is spent
   - Tax basis: FMV in PLN at moment of transaction
   - Example: Spend 0.5 BTC to pay for hosting service → Convert to PLN → Report as income

3. **Receiving Fiat from Binance Earn/Staking** (controversial)
   - Receiving staking rewards as fiat
   - Tax treatment: Generally treated as income (interpretation varies)
   - Conservative approach (used here): Ignore unless flagged

#### **NON-TAXABLE EVENTS** (Ignore for tax calculation)

1. **Crypto-to-Crypto Transactions**
   - Swapping BTC for ETH
   - Trading ALT for ALT
   - Reason: No fiat received, no taxable event under Polish law
   - Example: Convert 1 BTC → 10 ETH (ignored)

2. **Crypto Transfers**
   - Moving BTC from exchange to cold storage
   - Depositing crypto to exchange
   - Reason: Not a disposal, merely transfers ownership form
   - Example: Send 1 BTC to hardware wallet (ignored)

3. **Airdrops** (Conservative interpretation - configurable)
   - Receiving free crypto without purchase
   - Reason: Some argue not a taxable event if no receipt of fiat
   - Conservative interpretation: Ignore (default) | Progressive interpretation: Report as income

4. **Staking/Mining Rewards** (Controversial - configurable)
   - Earning crypto as staking rewards
   - Reason: Interpretation varies - could be:
     a) Not taxable (you didn't buy it)
     b) Taxable as income (you received value)
   - Conservative interpretation: Ignore (default) | Progressive: Report as income

---

### 2. Tax Base Calculation

#### **Key Principle: Global Cost Pooling (NOT FIFO)**

Polish tax law does **NOT** require FIFO (First-In-First-Out) cost basis method.

Instead, costs are **pooled globally**:

```
Taxable Income (Tax Base) = Revenue - Costs - Carried Forward Losses

Where:
- Revenue = Fiat received from crypto sales (all transactions combined)
- Costs = Fiat spent on crypto purchases (all transactions combined)
- Costs include purchase fees
- Carried losses = Unused losses from previous years
```

#### **Example: Global Cost Pooling**

```
2026 Transactions:
- 2026-01-15: Buy 1 BTC for 5,000 USD
- 2026-02-20: Buy 2 ETH for 2,000 USD
- 2026-03-10: Sell 1 BTC for 6,000 USD
- 2026-04-05: Sell 2 ETH for 2,500 USD

Calculation (with USD/PLN rate = 4.0):
- Total Revenue: (6,000 + 2,500) × 4.0 = 34,000 PLN
- Total Costs: (5,000 + 2,000) × 4.0 = 28,000 PLN
- Taxable Income: 34,000 - 28,000 = 6,000 PLN
- Tax Due (19%): 6,000 × 0.19 = 1,140 PLN

NOTE: Which BTC/ETH you "sold" doesn't matter - costs are pooled.
```

#### **Contrast with FIFO**

If FIFO were required (it's NOT in Poland):

```
FIFO would assume:
- 1 BTC purchased at 5,000 USD (cost: 5,000)
- 1 BTC sold at 6,000 USD (revenue: 6,000)
- Gain: 1,000 USD = 4,000 PLN

But with pooling (correct):
- All costs pooled: 28,000 PLN
- All revenue pooled: 34,000 PLN
- Net income: 6,000 PLN
```

---

### 3. Cost Basis (What Counts as "Cost")

#### **Costs Include:**

1. **Purchase Price**
   - Fiat spent to acquire crypto
   - Converted to PLN using NBP rate (T-1)
   - Example: Buy 1 BTC for 5,000 USD → costs = 5,000 USD

2. **Transaction Fees**
   - Exchange fees (Binance, Kraken, etc.)
   - Network fees (miner fees, etc.)
   - All in PLN value
   - Increases total cost basis

3. **Staking/Earning Withdrawals**
   - If you claim staking rewards as income, they add to cost basis
   - Example: Claim 100 USD in staking rewards → add to costs if reported as income

#### **Costs Do NOT Include:**

- Losses on other transactions (already accounted for)
- Unrealized losses (not a taxable event)
- Margin trading losses (separate category)
- Lost/stolen crypto (different tax treatment)

#### **Cost Accumulation (Year-to-Year)**

Unused costs carry forward:

```
2024:
- Costs: 10,000 PLN
- Revenue: 5,000 PLN
- Income: 0 (capped at 0)
- Loss: 5,000 PLN → Carry to 2025

2025:
- Costs: 8,000 PLN
- Revenue: 15,000 PLN
- Raw income: 7,000 PLN
- Minus carried loss: 5,000 PLN
- Taxable income: 2,000 PLN
- Tax due: 380 PLN
```

---

### 4. Exchange Rate Rules (T-1 Rule)

#### **The T-1 Rule**

Use the **NBP exchange rate from the day BEFORE (T-1) the transaction date**.

```
Transaction date: 2026-01-15
Rate used: NBP rate from 2026-01-14 (day before)
```

#### **Why T-1?**

- Standardizes exchange rates for transactions
- Uses official closing rate from previous day
- Avoids intra-day volatility disputes
- Consistent with Polish tax authority practice

#### **If T-1 Rate Unavailable (Weekend/Holiday)**

Search backwards for the most recent rate:

```
Transaction: 2026-01-18 (Sunday)
Check: 2026-01-17 (Saturday) → No rate
Check: 2026-01-16 (Friday) → Rate found → Use this rate

Max lookback: 10 business days
If no rate found within 10 days: Use fallback (1.0, log error)
```

#### **NBP Rate Lookup**

Official source: https://api.nbp.pl/

```
URL: https://api.nbp.pl/api/exchangerates/rates/A/{currency}/{date}/
Example: https://api.nbp.pl/api/exchangerates/rates/A/USD/2026-01-14/?format=json

Response: Mid rate (average of bid/ask)
Example: 4.0215 (means 1 USD = 4.0215 PLN)
```

#### **Stablecoins Still Require Conversion**

Even USDT (supposedly 1:1 to USD) must be converted:

```
USDT Balance: 5,000
Conversion: 5,000 USDT × USD_rate × (PLN/USD) = PLN value
Example: 5,000 USDT × 1.0 (USDT/USD) × 4.02 (USD/PLN) = 20,100 PLN
```

Reasoning: Polish law treats USDT as a foreign currency (USD), not as PLN.

---

### 5. Multi-Year Calculations

#### **Loss Carry-Forward**

Losses from one year can offset income in subsequent years:

```
Year 1: Loss of 5,000 PLN
Year 2: Income 8,000 PLN
Year 2 Tax Due: (8,000 - 5,000) × 0.19 = 570 PLN (not 1,520 PLN)
```

#### **Multi-Year Summary**

```
Annual Tax Report PIT-38:

2024:
- Revenue: 10,000 PLN
- Costs: 15,000 PLN
- Income: 0 (capped)
- Loss: 5,000 PLN → Carry to 2025

2025:
- Revenue: 20,000 PLN
- Costs: 12,000 PLN
- Gross Income: 8,000 PLN
- Minus carried loss: 5,000 PLN
- Taxable Income: 3,000 PLN
- Tax Due: 570 PLN

2026:
- Revenue: 15,000 PLN
- Costs: 25,000 PLN
- Gross Income: -10,000 PLN (loss)
- Loss: 10,000 PLN → Carry to 2027
```

---

### 6. Tax Rate & Filing

#### **Standard PIT Rate**

- **19%** flat rate on positive taxable income
- Applied to: Taxable Income = Revenue - Costs - Carried Losses

#### **Filing Requirements**

- Form: **PIT-38** (investment income)
- Due date: By April 30 of following year
- Required if: Crypto income > threshold (varies, typically 0 PLN)

#### **Common PIT-38 Sections**

- Section IIA: Income from sale of securities (relevant for crypto)
- Section IIB: Income from other sources
- Section III: Deductions and credits
- Section IV: Tax calculation (apply 19%)

---

### 7. Specific Transaction Types

#### **"Buy Crypto With Fiat" (Binance Operation)**

```
Operation: Buy Crypto With Fiat
Amount: 1 BTC
Currency: USD
Value: 5,000

Classification: COST (increases cost basis)
Treatment: Add to cost pool
Valuation: 5,000 USD × NBP_rate(T-1) = PLN
```

#### **"Fiat Withdraw" (Binance Operation)**

```
Operation: Fiat Withdraw
Amount: 6,000
Currency: USD

Classification: REVENUE (potentially taxable)
Treatment: Add to revenue pool
Valuation: 6,000 USD × NBP_rate(T-1) = PLN
```

#### **"Transaction Sold" (Binance Operation)**

```
Operation: Transaction Sold
Amount: 1 BTC
Currency: USD (if BTC → USD)
Value: 6,000

Classification: REVENUE (taxable)
Treatment: Add to revenue pool
Valuation: 6,000 USD × NBP_rate(T-1) = PLN
```

#### **"Transaction Buy" (Binance Operation - Crypto-Crypto)**

```
Operation: Transaction Buy
Amount: 10 ETH
Coin: ETH
Converted from: BTC

Classification: NON-TAXABLE (crypto-to-crypto)
Treatment: Ignore (not a disposal)
```

#### **"Transaction Spend" (Binance Operation - Crypto Purchase)**

```
Operation: Transaction Spend
Amount: 0.5 BTC
Spent on: Domain registration

Classification: REVENUE (disposal of crypto)
Treatment: Add to revenue pool
Valuation: 0.5 BTC × BTC/USD rate × USD/PLN rate = PLN
```

#### **"Binance Convert" (Binance Swap)**

```
Operation: Binance Convert
BTC → ETH, Amount: 1 BTC

Classification: NON-TAXABLE (internal swap)
Treatment: Ignore (not taxable per Polish law)
```

---

### 8. Edge Cases & Controversies

#### **Airdrop Treatment** (CONTROVERSIAL)

```
Conservative: IGNORE (default)
Reason: No fiat received, no sale occurred

Progressive: REPORT AS INCOME
Reason: Received economic benefit (crypto has value)

Module: Configurable via treat_airdrops_as_income
```

#### **Staking Rewards** (CONTROVERSIAL)

```
Conservative: IGNORE (default)
Reason: Interest/rewards not taxable until withdrawn

Progressive: REPORT AS INCOME
Reason: Accrual basis - income when earned

Module: Configurable via treat_staking_as_income
```

#### **Margin Trading Losses**

```
Treatment: DIFFERENT from spot trading
Reason: Complex derivatives, separate rules
Module: Currently NOT SUPPORTED (future enhancement)
```

#### **Wash Sales** (Not in Polish Law)

```
Status: NO WASH SALE RULE in Polish crypto taxation
Meaning: Can sell at loss, immediately repurchase (no penalty)
Advantage: Unlike US law, no "30-day rule"
```

---

### 9. Validation & Error Handling

#### **What This Module Validates**

✅ Missing or invalid transaction dates  
✅ Non-numeric amounts  
✅ Unknown operation types  
✅ Missing NBP exchange rates  
✅ Invalid currency codes  
✅ Zero amounts  
✅ Duplicate entries (warns but processes)

#### **What This Module Does NOT Validate**

❌ Completeness of data (missing transactions)  
❌ Accuracy of amounts (trust user input)  
❌ Legitimacy of transactions (is it really yours?)  
❌ Compliance with other tax rules (VAT, corporate tax, etc.)

---

### 10. Key Warnings & Disclaimers

### ⚠️ IMPORTANT DISCLAIMERS

1. **Not Legal Advice**
   - This tool assists with calculations
   - Tax law interpretation may vary
   - Consult professional tax advisor before filing

2. **Conservative Interpretation**
   - Default settings use conservative interpretation
   - Treats ambiguous situations as non-taxable
   - May underestimate tax liability

3. **Incomplete Data**
   - Ensure ALL transactions are included
   - Missing data = incorrect calculations
   - Tax authority will request documentation

4. **Law Changes**
   - Polish crypto tax law may change
   - 2026 regulations may differ from 2025
   - Verify current rules before filing

5. **Exchange Rates**
   - T-1 rule strictly enforced here
   - Different interpretation could apply
   - NBP rates are official but subject to change

6. **Manual Review**
   - Always review generated reports
   - Verify calculations make sense
   - Check for obvious errors

---

### 11. Reference Materials

#### **Official Sources**

- NBP Exchange Rates: https://api.nbp.pl/
- Polish Tax Authority: https://www.podatki.gov.pl/
- Tax Forms: https://www.podatki.gov.pl/podatnicy/pit/
- Crypto Tax Guidance: Search "PIT-38 kryptowaluty"

#### **Relevant Tax Forms**

- **PIT-38**: Investment income (crypto sales)
- **PIT-36**: Annual tax return
- **PIT-O**: Settlement form

---

### 12. Example Calculation Walkthrough

#### **Scenario**

```
2026 Cryptocurrency Trading:

2026-01-15 (Friday):
- Buy 1 BTC for 5,000 USD on Binance
- Fee: 50 USD
- Total cost: 5,050 USD

2026-02-20 (Friday):
- Buy 5 ETH for 2,000 USD
- Fee: 20 USD
- Total cost: 2,020 USD

2026-03-10 (Wednesday):
- Sell 1 BTC for 6,000 USD
- Proceeds: 6,000 USD

2026-04-05 (Saturday):
- Sell 5 ETH for 2,500 USD
- Proceeds: 2,500 USD

Exchange Rates (NBP, T-1):
- 2026-01-14: 1 USD = 4.00 PLN
- 2026-02-19: 1 USD = 4.05 PLN
- 2026-03-09: 1 USD = 4.02 PLN
- 2026-04-04 (Friday): 1 USD = 4.10 PLN (weekend, use Friday rate)
```

#### **Calculation Per Module**

```python
from processor import DataProcessor
from reporter import ReportGenerator

processor = DataProcessor()
report = processor.process(Path("binance_2026.csv"))

# Results for 2026:

Total Costs:
- BTC purchase: 5,000 USD × 4.00 = 20,000 PLN
- BTC fee: 50 USD × 4.00 = 200 PLN
- ETH purchase: 2,000 USD × 4.05 = 8,100 PLN
- ETH fee: 20 USD × 4.05 = 81 PLN
- Total costs: 28,381 PLN

Total Revenue:
- BTC sale: 6,000 USD × 4.02 = 24,120 PLN
- ETH sale: 2,500 USD × 4.10 = 10,250 PLN
- Total revenue: 34,370 PLN

Taxable Income:
- Revenue - Costs: 34,370 - 28,381 = 5,989 PLN

Tax Due (19%):
- 5,989 × 0.19 = 1,137.91 PLN

Report to submit on PIT-38:
- Section IIA: 34,370 PLN (income)
- Section III: 28,381 PLN (deduction)
- Taxable income: 5,989 PLN
- Tax: 1,137.91 PLN
```

---

**Document Version**: 1.0  
**Updated**: 2026-01-01  
**Applicable to**: Polish Tax Year 2026+

