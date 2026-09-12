# Part 6 — Which brand is actually the most generous?

Marketing's claim is wrong. PulseEats is the least generous of the three, not the most. Cleaned up,
PulseMart gives 2.300 points per dollar, PulseHome 2.000, PulseEats 1.750.

Their way of measuring it is also not trustworthy, and not only because the ranking came out
backwards. Points per dollar counts how many tokens a brand hands out, not what those tokens are
worth. So I can disprove the claim confidently. I can't tell you which brand is genuinely most
generous from this data at all.

## How the obvious calculation gets it backwards

The natural way to work out points per dollar is to add up all the points and divide by all the
spend. On the raw file that gives:

| | raw data | after cleaning |
|---|---|---|
| PulseHome | 1.948 — looks like the winner | 2.000 |
| PulseEats | 1.746 | 1.750 — actually the lowest |
| PulseMart | 0.906 — looks terrible | **2.300 — actually the winner** |

The order completely reverses. The genuine winner comes out looking like the worst brand by a factor
of two.

It's those 15 junk amounts from Part 1. Twelve of the fifteen belong to PulseMart, adding $6.83
million of imaginary spending to the bottom of its fraction. Fifteen rows out of 194,311 — 0.008% of
the file — flip the entire answer.

The part that bothers me is that nobody would question it. 0.906 looks like a perfectly plausible
number. A brand paying 0.9 points per dollar while its siblings pay 2 reads as a deliberate
positioning choice, and you'd write it up and move on. I only caught it because I checked what an
individual PulseMart transaction pays before writing the conclusion down: the typical row pays 2.30,
and an average can't sit below its own tenth percentile unless something is contaminating it.

## Why I trust the cleaned figure

Because the earning rate isn't an average that wobbles. It's exact.

| brand | Bronze | Silver | Gold | Platinum |
|---|---|---|---|---|
| PulseMart | 2.300 | 2.300 | 2.300 | 2.300 |
| PulseHome | 2.000 | 2.000 | 2.000 | 2.000 |
| PulseEats | 1.750 | 1.750 | 1.750 | 1.750 |

Identical to three decimal places in every tier, at every basket size from under $25 to over $200,
and in every channel. So this isn't one brand happening to have more Gold members than another. It's
a published rate per brand and nothing else.

That consistency is worth handing back to the business on its own. The rate depends on brand and
nothing else, which means a Platinum member earns exactly what a Bronze member earns, and the app
earns exactly what the till earns. A loyalty programme whose top tier gives no extra earning power
gives members no reason to climb it, and gives the business no lever over the customers it most wants
to keep. If marketing wants a generosity story, "we reward our best customers more" is the one they
currently can't tell — and that's a more fixable problem than the claim they were about to run.

One thing I checked because it could have undermined the answer: on 9.3% of transactions the brand
recorded against the transaction isn't the member's home brand. Using the transaction's brand gives
2.300 / 2.000 / 1.750. Using the member's home brand gives 2.261 / 2.002 / 1.787. PulseMart wins
either way, so the choice doesn't matter here.

## What I removed first

The 15 junk amounts, 2,012 refunds that had wrongly earned points, 1,995 duplicate transactions, and
the 1,514 rows where I'd estimated the points.

That last exclusion is deliberate and worth explaining. My estimate uses the brand's earning rate, so
leaving those rows in would let the calculation partly prove itself. Small effect, but it's the kind
of circularity that's embarrassing to have pointed out to you.

## Why the measure is the wrong question anyway

Points are a brand's own currency. Comparing points per dollar across brands is comparing salaries in
yen and dollars without knowing the exchange rate. A brand can hand out points at whatever rate it
likes and set what they're worth to match. 2.3 points worth a third of a cent is less generous than
1.75 points worth a full cent.

The break-even: a PulseEats point would need to be worth at least 1.31 times a PulseMart point for
PulseEats to genuinely come out ahead. That's not a far-fetched difference. It's well within the
range of ordinary programme design.

And nothing in this data says what a point is worth. Every transaction is a purchase, there's no
rewards catalogue, no discount column, and no link between points redeemed and any dollar figure I
could work backwards from.

## I did try to get round it

Declaring the question unanswerable without testing that would be lazy, so I checked whether
redemption behaviour hints at relative value. If a PulseEats point really were worth 1.31 times a
PulseMart one, people might spend them differently.

| brand | % of purchases involving a redemption | redeemed ÷ earned | typical redemption |
|---|---|---|---|
| PulseEats | 13.91% | 0.0995 | 82.3 points |
| PulseHome | 14.15% | 0.0957 | 89.4 points |
| PulseMart | 14.12% | 0.0902 | 96.5 points |

The meaningful column is the first one: people use the programme at essentially the same rate in all
three brands.

I'm deliberately not reading anything into the middle column. It's redeemed divided by earned, so a
brand handing out more points automatically gets a smaller fraction. PulseMart's lower figure is
mostly that arithmetic rather than anything customers are doing.

So: weak, inconclusive support for points being worth roughly the same across brands, and no positive
sign that PulseEats points carry the premium they'd need. It's muddied by how appealing each brand's
rewards are, and by a redemption column I already don't trust. It narrows the uncertainty without
closing it, and I'd still want the rewards catalogue before signing off any generosity claim.

## How confident I am

Very confident that marketing's claim is wrong. The rates are exact, they hold up under every cut of
the data I tried, and they don't depend on how transactions are attributed.

Not confident that PulseMart is genuinely the most generous. That's true for points handed out. It's
unanswerable for value delivered until someone tells us what a point is worth in each brand.

What I'd tell marketing: don't run the campaign as written. If you want a claim you can defend,
either say "points per dollar" and name PulseMart, or get me the redemption values and I'll work out
what a dollar actually earns back.

---

Workings in `output/section2_findings.txt`.

Previous: [Part 5 — Slack message](part5-slack-message.md) · Next: [Part 7 — Win-back list](part7-winback.md)
