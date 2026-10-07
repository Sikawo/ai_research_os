# Quality-of-Life Assessment Contract

## Scope

For every Tier 2 or better job, estimate whether the advertised compensation can support the user's configured household within the configured commute limit.

This is a planning estimate, not tax, legal, real-estate, education, or financial advice.

## Required inputs

- workplace address or best available worksite location;
- official salary range, or a clearly labeled estimate when the official range is absent;
- household adults and children with ages;
- commute limit and preferred modes;
- housing constraints, including minimum size and bedroom scenarios;
- public-school and private-school scenarios;
- childcare requirements;
- filing-status assumption and any known second income, if authorized.

## Commute-area selection

Identify three to five plausible residential areas within the configured commute limit.

Default behavior:

- use weekday peak driving time as the primary interpretation of the commute limit;
- also report transit feasibility where meaningful;
- do not treat a straight-line radius as equivalent to a travel-time boundary;
- mark commute estimates as approximate when a live routing source is unavailable;
- note tolls, parking, bridge or tunnel dependence, and severe peak-hour variability.

## Housing scenarios

For each selected area, estimate current rent for units that meet the configured minimum square footage:

- one-bedroom scenario;
- two-bedroom scenario.

Use current listings when available and HUD Small Area Fair Market Rent as a reference or reasonableness check. Report the sample size and date. Flag when the requested combination is scarce, when a one-bedroom may be impractical for the household, or when local occupancy rules require verification.

## Education and childcare scenarios

For each area, analyze:

1. Child below kindergarten age
   - full-time childcare, daycare, or preschool cost;
   - availability and wait-list risk when evidence is available.

2. Kindergarten-age or older child: public-school scenario
   - tuition assumed zero unless a special program charges fees;
   - assigned district or likely attendance boundary;
   - official state report-card indicators;
   - NCES enrollment and student-teacher context;
   - after-school care and school-calendar coverage when relevant;
   - housing premium or boundary uncertainty.

3. Kindergarten-age or older child: private-school scenario
   - representative nearby schools;
   - official published tuition and mandatory fees;
   - grade span, commute, and admissions timing;
   - do not infer quality solely from price or private status.

## Economic scenarios

Use the official salary lower bound, midpoint, and upper bound when available. Estimate:

- federal, payroll, state, and local taxes using current official rules where practical;
- monthly take-home pay;
- rent;
- childcare and education;
- food;
- health care;
- transportation, parking, and tolls;
- utilities, internet, and other necessities;
- estimated monthly surplus or deficit.

At minimum, report:

- one-bedroom + public kindergarten + childcare for younger child;
- two-bedroom + public kindergarten + childcare for younger child;
- two-bedroom + private kindergarten + childcare for younger child.

If spouse or partner income is unknown, use a single-income scenario and state the assumption. Optional second-income scenarios require explicit user configuration.

## Data-source hierarchy

Prefer:

1. official employer posting for salary and worksite;
2. IRS and state or local tax authorities for tax rules;
3. current rental listings plus HUD FY current-year FMR or SAFMR data;
4. MIT Living Wage Calculator and state childcare market-rate studies for baseline household expenses;
5. official state education report cards and NCES for public-school facts;
6. official school websites for private-school tuition;
7. official transit planners or live map routing for commute times.

Use aggregators only as supplementary evidence. Cite dates and distinguish current listings, official benchmarks, and estimates.

## Output

Every Tier 2+ report should include:

- salary basis and estimated take-home range;
- three to five commute-compatible residential areas;
- one-bedroom and two-bedroom rent ranges for 800+ square feet or the configured minimum;
- childcare cost for each pre-kindergarten child;
- public-school educational-quality summary;
- private-school tuition scenario;
- monthly surplus or deficit under each scenario;
- economic QOL verdict;
- educational QOL verdict;
- practical cautions and major unknowns;
- source links or citations.
