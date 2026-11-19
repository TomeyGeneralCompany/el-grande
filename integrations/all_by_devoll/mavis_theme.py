"""Shared MAVIS-style branding for El Grande's local browser interfaces.

Presentation only: no routes, financial calculations, forms, or persistence.
The high-contrast white-on-teal/red look matches the supplied MAVIS control-room
reference across jobs, cashbook, settings, and the bank-link page.
"""
CSS = r"""
:root {
  color-scheme: dark;
  --app-red: #c90028;
  --app-red-deep: #b60025;
  --panel-teal: #00c4bf;
  --panel-teal-deep: #009e9a;
  --white: #ffffff;
  --white-line: rgba(255,255,255,.55);
  --white-muted: rgba(255,255,255,.9);
  --ink: #ffffff;
  --muted: #ffffff;
  --bg: #c90028;
  --surface: #00c4bf;
  --line: rgba(255,255,255,.48);
  --forest: #c90028;
  --teal: #ffffff;
  --pale: #00aaa6;
  --danger: #ffffff;
}
html {scroll-behavior:smooth}
body {
  background:#c90028!important;
  color:#fff!important;
  font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;
  font-size:16px;
  line-height:1.45;
}
header {background:#c90028!important;color:white!important;border-bottom:1px solid rgba(255,255,255,.85)!important}
header .wrap {max-width:1112px;min-height:124px}
header,header strong,header small,header a {color:white!important}
.brand {gap:18px}
.brand strong {font-size:38px;letter-spacing:.012em;font-weight:750;line-height:1.15}
.brand small {font-size:15px;letter-spacing:0;color:#fff!important}
.mark {
  width:70px;height:70px;flex:0 0 70px;
  border:3px solid #fff;border-radius:50%;
  background:#00c4bf;color:#fff;
  font-family:Georgia,serif;font-size:24px;
  box-shadow:0 0 0 2px #00c4bf inset;
}
.topmeta,.topmeta a {color:#fff!important}
.topmeta a {border:1px solid #fff;background:transparent}
nav {background:#c90028!important;border-bottom:1px solid rgba(255,255,255,.28)!important;position:relative}
nav .wrap {max-width:1112px;gap:22px;min-height:49px;height:auto;flex-wrap:wrap;padding-top:9px;padding-bottom:9px}
nav a {color:#fff!important;font-size:14px}
nav a:hover,header a:hover {text-decoration:underline;color:#fff!important}
main {max-width:1112px!important;margin-top:24px;color:#fff}
a,a:visited {color:#fff}
a:hover {color:#fff;text-decoration:underline}
h1,h2,h3,h4,th,label,b,strong,summary,small {color:#fff}
h1 {font-size:30px;letter-spacing:0}
h2 {font-size:20px;letter-spacing:0}
h3 {font-size:18px}
.eyebrow,.muted,.small,.subline,.hint,.caption,
.metric label,.jobinfo span,.price span,.topmeta {color:#fff!important;opacity:1}
.intro {margin-bottom:20px}
.cards {gap:16px;margin-bottom:16px}
.metric,.panel,.ticket,.worksection,.price,.status-item,.empty,
section:not(.worksection),.notice,.ai {
  background:#00c4bf!important;
  color:#fff!important;
  border:0!important;
  border-radius:10px!important;
  box-shadow:none!important;
}
.metric,.panel,section:not(.worksection) {padding:20px}
.panel {margin:16px 0}
.metric strong {font-size:27px;letter-spacing:0}
.ticket {border:1px solid rgba(255,255,255,.35)!important;margin:12px 0;background:#00aaa6!important}
.ticket[open] {box-shadow:none!important}
.ticket>summary,.jobbody {color:#fff!important}
.jobbody,.minisection,details.inner {border-color:rgba(255,255,255,.55)!important}
.jobid,.pill,.pill.done,.pill.alert {
  background:#008d89!important;color:#fff!important;
  border:1px solid rgba(255,255,255,.55)!important;border-radius:7px
}
.chev,.jobinfo span,.jobname,.subline {color:#fff!important}
.worksection {border:1px solid rgba(255,255,255,.65)!important;background:rgba(0,125,121,.18)!important}
.price {border:1px solid rgba(255,255,255,.5)!important;background:#00aaa6!important}
.status-item {background:#00a9a5!important;border:1px solid rgba(255,255,255,.5)!important}
.status-item .dot {border:1px solid white}
.action,button,.button,button[type=submit],.details summary {
  background:#c90028!important;color:#fff!important;
  border:1px solid rgba(255,255,255,.85)!important;
  border-radius:7px!important;
  box-shadow:none!important;font-weight:700
}
.action.secondary,.action.danger {background:#b60025!important;color:#fff!important}
.action:hover,button:hover,.button:hover,.details summary:hover {
  background:#a90022!important;color:#fff!important
}
input,select,textarea {
  background:#008f8b!important;
  color:#fff!important;border:1px solid rgba(255,255,255,.78)!important;
  border-radius:7px!important;
  font:inherit
}
input::placeholder,textarea::placeholder {color:rgba(255,255,255,.82)}
input:focus-visible,select:focus-visible,textarea:focus-visible,
button:focus-visible,.action:focus-visible,summary:focus-visible {
  outline:3px solid #fff!important;outline-offset:2px
}
input[type=checkbox],input[type=radio] {accent-color:#c90028}
select option {background:#008f8b;color:#fff}
table {width:100%;border-collapse:collapse;color:#fff}
th,td {
  border:0!important;border-bottom:1px solid rgba(255,255,255,.65)!important;
  padding:9px 8px;text-align:left;vertical-align:top
}
thead th {font-weight:750;color:#fff}
.list li,.catalog li {border-color:rgba(255,255,255,.55)}
footer {border-top:1px solid #fff;color:#fff}
@media(max-width:840px) {
  header .wrap {min-height:100px}
  .brand strong {font-size:30px}
  .mark {width:58px;height:58px;flex-basis:58px}
}
@media(max-width:560px) {
  header .wrap {min-height:86px}
  .brand strong {font-size:26px}
  .brand small {font-size:12px}
  .mark {width:48px;height:48px;flex-basis:48px;font-size:17px}
  .metric,.panel,section:not(.worksection) {padding:15px}
  .cards {grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
}
"""
