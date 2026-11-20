# Review of the seven-year-old ZeverSolar code

These are defects in the **supplied source**, not hypothetical changes.

| Area | Original fault | Change / verification |
| --- | --- | --- |
| Connectivity | `ping -n 1` is Windows-specific, not Raspberry Pi-friendly. | Removed ping dependency; directly retry `GET /home.cgi` with backoff. |
| Connectivity | On repeated connection failures, a high last power value led to a tight retry loop; the `ts.hour` early-morning sleep calculation was wrong. | All request/parse failures back off, with an upper limit of 300 seconds. |
| HTTP | Network reads had no timeout, and non-2xx HTTP responses were not explicitly rejected. | 10-second timeout, `raise_for_status`, retry on `requests.RequestException`. |
| Gateway parser | `(parts[1] == 3)` compared a string with an integer. | Check string codes `"0"` and `"3"`; unit tested. |
| Gateway parser | The meter values were placed in a local `meter` dictionary, but `results['meter']` remained empty. | Return parsed meter values; unit tested. |
| Gateway parser | No length/number validation: malformed responses could crash the collector or be saved as bad data. | Check row count, field counts, numeric power/energy. Bad samples are skipped and retried. |
| Energy workaround | `correct_E_Today` indexed the second split field without checking for a dot and retained string values. | Accept whole numbers, preserve the device's one-decimal workaround, store validated float. |
| SQLite | Database setup could fail on reruns because the original `CREATE TABLE` was not idempotent; warning claimed data was deleted when it wasn't. | `CREATE TABLE IF NOT EXISTS` plus indexes. Existing readings are never dropped. |
| SQLite | Each inverter sample was individually committed. | Insert multiple inverters per poll in one transaction. |
| Plot date boundaries | `--to YYYY-MM-DD` was used as a strict upper bound at midnight, excluding that date. | Treat `--to` as inclusive, ending at next-day midnight. |
| Plotting | `--totals` wasn't declared in the usage options, multi-inverter bars overlapped, and `mdates.DateLocator()` was not valid. | `argparse` CLI; individual labelled series; `AutoDateLocator`/`ConciseDateFormatter`. |
| Plotly | The unfinished Cloud prototype contained an embedded, reportedly revoked API key. | Removed the credential and retired that cloud prototype. The replacement is entirely local. |
| Packaging | Packages pinned to 2018 versions included old Matplotlib and NumPy, unsuitable as a lightweight modern Pi setup. | Runtime dependency reduced to Requests; plotting optional; Bootstrap packaged locally. |

**Important design decisions:** Full-day totals use `MAX(E_TODAY)` per inverter-day. Hourly and selected-hour reports **cannot truthfully reconstruct an outage** from the source data; only meter deltas spanning ≤ five minutes are allocated, with large gaps shown as unknown. Values shown for a partial week/month/year are sums of **observed** days, not claims about the missing ones.

**Still to verify in your environment:** Compatibility with your inverter's actual `home.cgi` payload, available disk space and query performance on your Raspberry Pi hardware, and proper local timezone/sunrise configuration. No physical inverter or Raspberry Pi was provided for a live test.
