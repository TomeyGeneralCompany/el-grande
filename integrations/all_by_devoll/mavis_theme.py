"""Shared MAVIS-style branding for El Grande's local browser interfaces.

Presentation only: no routes, financial calculations, forms, or persistence.
The high-contrast white-on-teal/red look matches the supplied MAVIS control-room
reference across jobs, cashbook, settings, and the bank-link page.
"""
CSS = r"""
:root {
  color-scheme: dark;
  --app-red: #e09915;
  --app-red-deep: #cf870e;
  --panel-teal: #00c4bf;
  --panel-teal-deep: #009e9a;
  --white: #ffffff;
  --gold-background: #e09915;
  --logo-red: #c9031e;
  --white-line: rgba(255,255,255,.55);
  --white-muted: rgba(255,255,255,.9);
  --ink: #ffffff;
  --muted: #ffffff;
  --bg: #e09915;
  --surface: #00c4bf;
  --line: rgba(255,255,255,.48);
  --forest: #e09915;
  --teal: #ffffff;
  --pale: #00aaa6;
  --danger: #ffffff;
}
html {scroll-behavior:smooth}
body {
  background:#e09915!important;
  color:#fff!important;
  font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;
  font-size:16px;
  line-height:1.45;
}
header {background:#e09915!important;color:white!important;border-bottom:1px solid rgba(255,255,255,.85)!important}
header .wrap {max-width:1112px;min-height:124px}
header,header strong,header small,header a {color:white!important}
.brand {gap:18px}
.brand strong {font-size:38px;letter-spacing:.012em;font-weight:750;line-height:1.15}
.brand small {font-size:15px;letter-spacing:0;color:#fff!important}
.mark {
  width:70px;height:70px;flex:0 0 70px;
  border:3px solid #fff;border-radius:50%;
  background:#c9031e;color:#fff;
  font-family:Georgia,serif;font-size:24px;
  box-shadow:0 0 0 2px #00c4bf inset;
}
.topmeta,.topmeta a {color:#fff!important}
.topmeta a {border:1px solid #fff;background:transparent}
nav {background:#e09915!important;border-bottom:1px solid rgba(255,255,255,.28)!important;position:relative}
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
  background:#e09915!important;color:#fff!important;
  border:1px solid rgba(255,255,255,.85)!important;
  border-radius:7px!important;
  box-shadow:none!important;font-weight:700
}
.action.secondary,.action.danger {background:#cf870e!important;color:#fff!important}
.action:hover,button:hover,.button:hover,.details summary:hover {
  background:#b77907!important;color:#fff!important
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

/* All by Devoll gold-and-teal design, with a red parent-company logo corner.
   Matches the supplied reference without adding textures or gradients. */
header,nav {background:#e09915!important}
body {background:#e09915!important}
.panel,.metric,section:not(.worksection) {background:#00beb6!important}
button,.button,.action,.details summary,
.action.secondary,.action.danger,button[type=submit] {background:#00a9a2!important}
button:hover,.button:hover,.action:hover,.details summary:hover {background:#008e87!important}
.brand-mark-parent {
  border:3px solid #00c4bf!important;
  border-radius:15px!important;
  background:#c9031e!important;
  display:flex;align-items:center;justify-content:center;
  width:208px;max-width:100%;height:144px;
}
.brand-mark-parent img {width:128px;height:128px;object-fit:contain}
.brand-mark-devoll img {width:110px;height:110px;object-fit:contain}
.dashboard-layout {display:grid;grid-template-columns:233px minmax(0,1fr);gap:22px;max-width:1462px;margin:auto;padding:0 15px}
.sidebar {min-width:0;padding:0}
.sidebar-brand {border-radius:15px;border:3px solid #00c4bf;background:#c9031e;
height:145px;display:flex;align-items:center;justify-content:center;margin-bottom:19px}
.sidebar-brand img {width:128px;height:128px;object-fit:contain}
.sidebar-links {display:flex;flex-direction:column;gap:11px}
.sidebar-links a {background:#00beb6;color:white!important;display:block;border-radius:13px;
font-size:18px;font-weight:700;padding:16px 19px;text-decoration:none}
.sidebar-links a:hover {background:#009f99}
.sidebar-bottom {border-top:3px solid #00c4bf;margin:50px 10px 0;padding-top:18px;color:white;line-height:1.5}
.dashboard-workspace {min-width:0}
.dashboard-header {display:flex;align-items:center;justify-content:space-between;gap:18px;min-height:145px}
.dashboard-title {display:flex;gap:24px;align-items:center;min-width:0}
.dashboard-title .separator {height:100px;border-left:3px solid white;flex:none}
.dashboard-title strong {font-size:64px;line-height:1.05;letter-spacing:0;font-weight:800}
.dashboard-title small {display:block;font-size:17px;color:white}
.dashboard-company {display:flex;align-items:center;gap:16px;text-align:right}
.dashboard-company strong {font-size:24px}
.dashboard-company small {display:block;color:white;font-size:15px}
.dashboard-main {margin:0!important;padding:0!important;max-width:none!important}
.dashboard-overview {display:grid;grid-template-columns:1fr 1fr;gap:16px}
.dashboard-overview .overview-wide {grid-column:1/-1}
.dashboard-overview .panel {padding:19px!important;margin:0!important}
.dashboard-overview h2 {font-size:30px;line-height:1.2;margin:0 0 14px}
.overview-rows {display:grid;grid-template-columns:minmax(125px,.8fr) minmax(0,1.4fr);
gap:6px 18px;font-weight:600}
.overview-rows .overview-value {font-weight:500;overflow-wrap:anywhere}
.overview-rows .overview-money {text-align:right;font-weight:650}
.overview-money-grid {grid-template-columns:minmax(0,1.35fr) minmax(120px,.65fr)}
.overview-rows .muted {color:#fff}
.dashboard-overview .panel table {width:100%}
.overview-empty {color:white;margin:0}
.dashboard-divider {height:1px;background:rgba(255,255,255,.55);margin:14px 0}
.dashboard-activity {list-style:disc;margin:0;padding-left:29px}
.dashboard-activity li {margin:7px 0;overflow-wrap:anywhere}
.dashboard-jobdesk {margin-top:24px}
.dashboard-jobdesk > .intro {display:none}
.dashboard-jobdesk .metric {background:#00beb6!important}
.dashboard-jobdesk .cards {margin-top:14px}
.dashboard-header-rule {border:0;border-bottom:1px solid rgba(255,255,255,.8);margin:0 0 21px}
@media(max-width:1120px) {
 .dashboard-layout {grid-template-columns:190px minmax(0,1fr)}
 .dashboard-title strong {font-size:46px}
 .dashboard-title small {font-size:14px}
 .dashboard-company strong {font-size:18px}
 .sidebar-brand {height:127px}
 .sidebar-brand img {width:112px;height:112px}
 .sidebar-links a {font-size:15px;padding:13px}
}
@media(max-width:800px) {
 .dashboard-layout {display:block}
 .sidebar-brand {display:none}
 .sidebar-links {flex-direction:row;flex-wrap:wrap;margin:8px 0 15px;gap:7px}
 .sidebar-links a {font-size:13px;padding:9px 12px}
 .sidebar-bottom {display:none}
 .dashboard-header {min-height:110px}
 .dashboard-company {gap:8px}
 .brand-mark-devoll img {width:68px;height:68px}
 .dashboard-title strong {font-size:34px}
 .dashboard-title small,.dashboard-company small {font-size:11px}
 .dashboard-overview h2 {font-size:22px}
}
@media(max-width:560px) {
 .dashboard-header {align-items:flex-start;padding-top:10px}
 .dashboard-title .separator {height:70px}
 .dashboard-title {gap:9px}
 .dashboard-title strong {font-size:25px}
 .dashboard-company {flex-direction:column-reverse;align-items:flex-end;text-align:right}
 .dashboard-company strong {font-size:13px}
 .dashboard-overview {grid-template-columns:1fr}
 .dashboard-overview .overview-wide {grid-column:auto}
}
