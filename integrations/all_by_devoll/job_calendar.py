"""Local appointments for existing shop tickets."""
import calendar
from collections import Counter
from datetime import date, datetime, time
from html import escape
from zoneinfo import ZoneInfo

DDL = """
CREATE TABLE IF NOT EXISTS job_appointments (
    ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS job_appointments_by_date
ON job_appointments(appointment_date, appointment_time, ticket_id);
"""

ACTIVE = "finalized_at IS NULL AND status IN ('new','estimating','quoted','approved','in_progress')"

CSS = """
#calendar .calendar-heading, #calendar .calendar-nav {
    display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
}
#calendar .calendar-heading { justify-content: space-between; }
#calendar .calendar-month { margin-top: 16px; }
#calendar .calendar-week {
    display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px;
    margin-bottom: 4px; text-align: center;
}
#calendar .calendar-day { padding: 5px 0; border: 1px solid #ffffff80; border-radius: 5px; }
#calendar .calendar-day[aria-current] { outline: 2px solid white; outline-offset: -2px; }
#calendar .calendar-day a { display: block; background: #006d69; font-weight: 700; }
#calendar .calendar-agenda { list-style: none; padding: 0; margin: 0; }
#calendar .calendar-agenda li { padding: 8px 0; border-top: 1px solid #ffffff80; }
#calendar .calendar-entry { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
#calendar .calendar-entry form { margin: 0; }
#calendar .calendar-entry a { text-decoration: underline; }
#calendar .calendar-editor { margin-top: 14px; }
#calendar .calendar-month + h3 { margin-top: 18px; }
"""

def today():
    return datetime.now(ZoneInfo("America/Detroit")).date()

def parse_month(value, current):
    try:
        year, month = value.split("-")
        first = date(int(year), int(month), 1)
        if value == first.isoformat()[:7]:
            return first
    except ValueError:
        pass
    return current.replace(day=1)

def schedule(con, ticket_id, day_text, time_text):
    try:
        day = date.fromisoformat(day_text)
        at = time.fromisoformat(time_text)
        if day_text != day.isoformat() or time_text != at.isoformat(timespec="minutes"):
            raise ValueError
    except ValueError as error:
        raise ValueError("Enter an appointment date and local time.") from error
    updated = con.execute("""INSERT INTO job_appointments(ticket_id, appointment_date, appointment_time)
        SELECT id, ?, ? FROM tickets WHERE id = ? AND """ + ACTIVE + """
        ON CONFLICT(ticket_id) DO UPDATE SET appointment_date = excluded.appointment_date,
        appointment_time = excluded.appointment_time""", (day_text, time_text, ticket_id))
    if not updated.rowcount:
        raise ValueError("Choose an open job to schedule.")
    return day

def appointment_form(jobs, default_day, selected=None):
    if not jobs:
        return '<p><a href="#new">Create a job</a> to schedule its appointment.</p>'
    selected_id = selected["ticket_id"] if selected else None
    day = selected["appointment_date"] if selected else default_day.isoformat()
    clock = selected["appointment_time"] if selected else ""
    options = ['<option value="">Choose an open job</option>']
    for job in jobs:
        job_id = job["id"]
        description = job["customer"] or job["service"] or "Service request"
        mark = " selected" if job_id == selected_id else ""
        options.append(f'<option value="{job_id}"{mark}>ABD-{job_id:06d} · {escape(description)}</option>')
    return (
        '<form class="calendar-editor" method="post" action="/appointments/save">'
        '<div class="fields"><label>Job<select name="ticket_id" required>'
        + "".join(options)
        + f'</select></label><label>Date<input type="date" name="date" value="{day}" required></label>'
        + f'<label>Time<input type="time" name="time" value="{clock}" required></label></div>'
        '<div class="footactions"><button class="action" type="submit">Save appointment</button>'
        '<a href="#new">Create a job</a></div></form>'
    )

def render(con, requested_month="", edit_ticket=""):
    current = today()
    first = parse_month(requested_month, current)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    current_month = first.isoformat()[:7]
    jobs = con.execute("SELECT id, customer, service FROM tickets WHERE " + ACTIVE + " ORDER BY id DESC").fetchall()
    month_jobs = con.execute("""SELECT a.*, t.customer, t.service, t.status, t.finalized_at
        FROM job_appointments AS a JOIN tickets AS t ON t.id = a.ticket_id
        WHERE a.appointment_date BETWEEN ? AND ?
        ORDER BY a.appointment_date, a.appointment_time, a.ticket_id""",
        (first.isoformat(), last.isoformat())).fetchall()
    open_ids = {job["id"] for job in jobs}
    selected = next((job for job in month_jobs if str(job["ticket_id"]) == edit_ticket
                     and job["ticket_id"] in open_ids), None)

    nav = []
    if first > date.min:
        previous = date.fromordinal(first.toordinal() - 1)
        nav.append(f'<a class="action secondary" href="/?calendar={previous.isoformat()[:7]}#calendar">Previous</a>')
    nav.append('<a class="action secondary" href="/#calendar">Today</a>')
    if last < date.max:
        following = date.fromordinal(last.toordinal() + 1)
        nav.append(f'<a class="action secondary" href="/?calendar={following.isoformat()[:7]}#calendar">Next</a>')

    week_days = "".join(f"<strong>{day}</strong>" for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
    totals = Counter(row["appointment_date"] for row in month_jobs)
    weeks = []
    for week in calendar.Calendar().monthdayscalendar(first.year, first.month):
        cells = []
        for number in week:
            if not number:
                cells.append('<span aria-hidden="true"></span>')
                continue
            day = first.replace(day=number)
            iso = day.isoformat()
            today_attr = ' aria-current="date"' if day == current else ""
            label = f'<time datetime="{iso}">{number}</time>'
            if totals[iso]:
                label = (f'<a href="#appointments-{iso}" aria-label="{day:%B} {number}, '
                         f'{totals[iso]} scheduled">{label}<br>{totals[iso]}</a>')
            cells.append(f'<span class="calendar-day"{today_attr}>{label}</span>')
        weeks.append('<div class="calendar-week">' + "".join(cells) + "</div>")

    agenda = []
    listed_date = None
    for row in month_jobs:
        ticket_id = row["ticket_id"]
        iso = row["appointment_date"]
        day = date.fromisoformat(iso)
        clock = time.fromisoformat(row["appointment_time"]).strftime("%I:%M %p").lstrip("0")
        label = escape(row["customer"] or row["service"] or "Service request")
        label = f'<a href="/ticket/{ticket_id}">{label}</a>'
        anchor = f' id="appointments-{iso}"' if iso != listed_date else ""
        listed_date = iso
        edit = (f'<a href="/?calendar={current_month}&amp;edit_appointment={ticket_id}#calendar-form">Reschedule</a>'
                if ticket_id in open_ids else "")
        status = ""
        if row["finalized_at"] or row["status"] == "cancelled":
            status = " · " + ("Cancelled" if row["status"] == "cancelled" else "Completed")
        agenda.append(
            f'<li{anchor}><div class="calendar-entry"><strong>{day:%a, %b} {day.day} · {clock}</strong>'
            f'<span>ABD-{ticket_id:06d} · {label}{status}</span>{edit}'
            '<form method="post" action="/appointments/remove">'
            f'<input type="hidden" name="ticket_id" value="{ticket_id}">'
            f'<input type="hidden" name="calendar" value="{current_month}">'
            '<button class="action secondary" type="submit">Remove appointment</button>'
            "</form></div></li>"
        )

    default_day = current if current.replace(day=1) == first else first
    form_title = "Reschedule appointment" if selected else "Schedule a job"
    agenda_html = '<ul class="calendar-agenda">' + "".join(agenda) + "</ul>" if agenda else "<p>No appointments this month.</p>"
    return (
        '<section class="panel overview-wide" id="calendar"><div class="calendar-heading">'
        '<h2>Job calendar</h2><div class="calendar-nav">' + "".join(nav) + "</div></div>"
        f'<div class="calendar-month"><h3>{first:%B} {first.year}</h3>'
        f'<div class="calendar-week">{week_days}</div>' + "".join(weeks) + "</div>"
        '<h3>Appointments this month</h3>' + agenda_html
        + f'<div class="minisection" id="calendar-form"><h3>{form_title}</h3>'
        + appointment_form(jobs, default_day, selected) + "</div></section>"
    )
