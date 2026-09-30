# How TrackWrestling behaves

Everything here was established against the live site in 2026. Most of it cannot be guessed,
and most of it **fails silently**: a 200 with nothing useful in it. When you learn something
new about the site, add it here in the same change.

## Sessions and empty shells

- Every tournament page needs a **viewer session**. One GET to
  `/{site}/VerifyPassword.jsp?tournamentId=…&userType=viewer&userName=&password=` sets a
  cookie. After that the literal `twSessionId=zyxwvutsrq` is accepted in every URL. The
  identity lives in the cookie jar, which is why each tournament has its own `ClientSession`.
- Without a session, TrackWrestling answers **200 with an empty shell**: about 1.2KB that loads
  `GoToLogin.js` and has no visible text.
- A tournament requested under the **wrong event type** gets a different empty shell: about
  1.1KB of analytics scripts, again no visible text.
- `utils/session_manager.is_stub()` treats a page under 4KB with no visible text as a shell.
  `fetch()` re-opens the session once, then raises `TournamentUnavailable` (a 404 from the API).
  A real page is never that small and empty: even an empty mat-assignment page is about 8.6KB
  and says "Mat Assignment Display LOADING...".
- Sessions expire. That is why the cache is not trusted blindly.
- `TIM` in every URL is a **cache-busting millisecond timestamp**, not a tournament id. It is 13
  digits; real tournament ids are 9 or 10. People paste it as an id, so `server._resolve`
  rejects anything from 10^12 up.

## Event types and site paths

| `EventType` | id | site path | alias |
| --- | --- | --- | --- |
| PREDEFINED | 1 | `predefinedtournaments` | `predefined` |
| OPEN | 2 | `opentournaments` | `open` |
| TEAM | 3 | `teamtournaments` | `team` |
| FREESTYLE | 4 | `freestyletournaments` | `freestyle` |
| SEASON | 5 | `seasontournaments` | `season` |

The id alone does not say which path a tournament lives under. Search results carry the type id.

## Search: `Login.jsp`

- It wants the **whole form**, every field including the empty ones (see `search_tournaments`).
- Each hit is `javascript:eventSelected(<id>,'<name>',<typeId>,'<logo>'[, …])`.
  - Names contain commas ("Some Open, 3rd-4th Grade") and brackets ("… (Boys)"). Split the
    arguments respecting quotes (`_split_js_args`), and capture them greedily to the end of
    the statement.
  - An apostrophe in a name is written as a **backtick**: "Women`s National Championships".
    Search turns it back into `'`. Handle `\` escapes too, in case they appear.
- Dates appear as `03/19/2026 - 03/21/2026`, or `03/19 - 03/21/2026` where the start borrows
  the end's year. A range across New Year (`12/30 - 01/02/2027`) needs the start rolled back a
  year. `_parse_date_range` handles all three; use it for any new date field.

## Tournament hub: `TournamentHub.jsp`

`.hub-nav > ul > li:first-child .content` holds the name (`h3`), the logo, the dates (first
`p`) and the venue (second `p`: name, street, "City, ST 12345").

## Mat assignments: `MB_MatAssignmentDisplay.jsp`

- It only has content **while an event is running**. After that it is an empty page, so the
  parser is tested offline (`tests/test_matches.py`), not live.
- One `<tr>` with three `<td>`s per match:
  - status colour: `#00FF66` in progress, yellow on deck, anything else in the hole
  - "Mat N" and the bout number
  - the details: weight in `div[data-short-title]`, the round, and two `<font data-wrestler-id
    data-team-id>` wrestlers
- Each wrestler is **three `span[data-short-title]` in order: first name, last name, team**.
  The attribute holds the abbreviation, the text holds the full value. Picking spans by any
  other rule gave every wrestler their first initial as a team.

## Bracket viewer: `BracketViewer.jsp`

The dropdown data is a series of `str = "…"` assignments inside the script that builds
`new Pile()`, tilde-delimited:

| Block | Fields per entry | Notes |
| --- | --- | --- |
| templates (first) | 7: bracketId, templateId, name, width, height, font, pages | pages is `id,name,id,name…` |
| divisions (older pages only) | 2: id, name | gone from 2026 pages |
| weights | 3: weightId, name, bracketId (older pages: 4, with a leading divisionId) | weight ids are large (>1,000,000) |
| bracket types (last) | comma list of ids | |

Identify blocks by **role** (first, last, what's between). The divisions block disappearing
shifted every index by one and broke the old positional parser. The weights shape follows from
whether a divisions block is present. Don't guess it from the data: numeric weight names make a
12-entry list fit both shapes.

## Bracket sheets

- **`Bracket.jsp`** (a viewable page): `groupId`, `bracketWidth`, `bracketHeight`,
  `bracketFontSize`, `includePages`, `templateId` are the parameters BracketViewer's own
  JavaScript uses (`generate_bracket_url`). The older `chartWidth`/`chartHeight` names are
  ignored.
- **`AjaxFunctions.jsp?function=getBracket`** (the same bracket, no page chrome): needs its
  **full** parameter set (`groupId`, `chartId`, `width`, `height`, `font`, `includePages`,
  `templateId`), or it answers "There has been an error" without saying what's missing.
  `includePages` is honoured, and empty means every page.
- One request per weight. No URL returns every weight at once: comma-separated, omitted,
  `0` and `all` group ids were all tried.

### Sheet markup (`parsers/brackets.py`)

- `class='full-line' data-wrestler-id data-team-id` is a **first-round slot**, in bracket
  order. `class='half-line'` draws later rounds and pre-rounds.
- **Three entry-line formats, and which one a sheet uses is per tournament:**

  ```
  D1     (1) Luke <a class='plain' …>Lilledahl</a>, PSU, 25-0
  D2/W   (1) Isaiah Gamez<br>Adams St., 27-3
  D3     (1) Christian Guzman<br>North Central (IL) (5)
  ```

  The name ends at the `<br>` where there is one, otherwise at the first comma. Don't split on
  the profile link: a wrestler without a profile has none. D3's trailing `(5)` is a regional
  qualifying rank; strip only a digits-only parenthesis so `(IL)` survives. An unseeded slot
  has `&nbsp;` where the seed goes.
- **Pigtail entrants** are wrestlers mentioned on the sheet who hold no first-round slot. Find
  them by wrestler id. D1 and D3 print them as a surname and team ("Schafer, BLOO"), so they
  are flagged `partial`.
- **Bout numbers** come from the link *text* of `openBoutSheet(n,'X')`. The first argument
  repeats across pages and is not an id.
- **Routes**: "Loser of 19", "To top of 265", "To bottom of 11". They are the one part of a
  bracket's shape that differs by division (D2 sends pigtail winners to seeds 8 and 7, D3 to
  seeds 1-5), so they are returned verbatim.
- Sheets **truncate long names** ("Shane Cartagena-Wals"); the results page does not.

## Results: `RoundResults.jsp`

- Every bout of a tournament in **one request** (640 for 2026 D1, about 89KB).
- A **POST** where the ids go in the **query string** (`roundId`, `groupId`, `displayResult=Y`)
  and the box fields in the **body** (`roundIdBox`, `groupIdBox`, `fontSizeBox`,
  `displayFormatBox`, `includeByesBox`, `patternBox`). That's how the page's own
  `viewSchedule()` builds it.
- **`displayFormatBox` must be `1` or `2`.** Left empty, the page renders an empty results
  container and no error.
- The viewer must name a round or a weight; "all of it" means passing every weight id. An empty
  `roundId` means every round.
- Markup: `<section class='tw-list'><h1>round</h1>` then `<h2>weight</h2><ul><li>…</li></ul>`
  **repeated for each weight**. Pairing one `h1` with one `h2` loses all but the first weight.
- A line: `label - NAME (School) 25-0 won by <method> over NAME (School) 19-7 (<result>)`.
  Split on the verb (`won by` / `won in`); the method has many forms.
- Result codes seen in 2026: `Dec`, `MD`, `Fall`, `TF-1.5`, `SV-1`, `SV-2`, `TB-1`, `TB-2`,
  `TB-3`, `2-OT`, `Inj.`, `DQ`, `M. For.`, `MFFL`, `For`.
  - Keep them **verbatim**. `M. For.` and `MFFL` are the same outcome written two ways; `For`
    is a plain forfeit.
  - Women's wrestling is freestyle: no `MD`, and far more tech falls.
- **Bout numbers are not on this page.** Join to the bracket sheet by round and wrestler pair
  if you need them.
- Two polls seconds apart return different bytes (embedded `TIM` and session state). For change
  detection, compare parsed results, not responses.

## Reference tournaments (finished, so their data is stable)

| Championship | id | type | bouts | bracket sheet |
| --- | --- | --- | --- | --- |
| 2026 NCAA Division I | 931299132 | predefined | 640 | 32-man, all seeded, 1 pigtail, pages 0/2/3 |
| 2026 NCAA Division II | 954920132 | predefined | 340 | 16-man, 8 seeded, 2 pigtails |
| 2026 NCAA Division III | 954922132 | predefined | 400 | 16-man, 11 seeded, 5 pigtails |
| 2026 NCAA Women's | 965471132 | predefined | 340 | 16-man, 8 seeded, 2 pigtails |

## Known but deliberately unused

`TextCam.jsp?eventType=predefined&eventId=<tournament>&matchId=<id>` gives a per-match box
score (`matchId` comes from `watchVideo(<id>)` on the bracket sheet). It costs one request per
bout, 640 for D1, so don't build anything that loops over it.
