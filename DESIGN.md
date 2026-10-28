# ElectionsUSA design system (reference: america.gov, Sept 2026 relaunch)

## What the reference does (from launch coverage and design reviews)
- Opens with two words in a large, high-contrast serif with tight spacing ("Hello, America"),
  no seals, no menus, no hero photo. One search field beneath, with an example question as the
  placeholder doing the onboarding.
- Supporting copy and interface text in a clean grotesque sans-serif.
- The product promises (free, no ads, privacy) are set as the largest type on the page:
  typography carries the policy statement.
- Every answer is sourced; links to originals are part of the design, not a footnote.
- Minimalist: generous whitespace, hairline rules, almost no colour, no decorative imagery.

## How ElectionsUSA adapts it
| Reference | ElectionsUSA |
|---|---|
| "Hello, America" serif greeting | Serif headline that asks the site's question: *"How is 2028 looking?"* |
| One search field, example question | One "Ask" field that searches the site's pages, candidates and pollsters client-side; six suggested questions as chips |
| Promises in big type | "Free. Open data. Every number linked to its source." set in display serif |
| Answers cite official sources | Every poll row links to the pollster; API/CSV links on every page |
| No photography | No stock photos or candidate portraits: the charts and the numbers are the imagery |
| Minimal chrome | 56px header: serif wordmark, five text links, compact search; no boxed cards, hairline rules only |

Where we deliberately differ: the site is ad-funded, so ads are present but quiet (a hairline-boxed slot
labelled "Advertisement", never inline with data); we cannot promise "no ads", so we promise "open data".
Nothing imitates government identity: no official-website banner, no seals, no .gov language.

## Tokens
- Paper `#fbfbf9`, ink `#0e0e0f`, secondary ink `#3a3a3c`, muted `#77777a`, hairline `#e4e3de`
- Accent blue `#1d3f8f` (links, Democratic series), accent red `#b3262e` (Republican series)
- Display: Instrument Serif (400), letter-spacing −0.02em, sizes 44–112px
- Text/UI: Inter 400/500/600, 16px/1.55, tabular numerals
- Rhythm: 8px base, section spacing 64–96px, max content width 1080px, prose 70ch
- Dark mode: inverted paper/ink, same accents lightened
