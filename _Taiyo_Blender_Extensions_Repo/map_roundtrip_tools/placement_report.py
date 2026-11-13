"""Problems found while planning a Placement CSV: where they are, what they are, what was done about them."""
from dataclasses import dataclass

REPORT_TEXT = 'MRT Placement Report'
MAX_REPORT_LINES = 5000

LAST_ISSUES = []  # issues of the last Preview / Replace, shown by the Import panel


@dataclass
class Issue:
    kind: str           # short code such as 'bad_number', 'missing_mesh', 'unknown_id'
    message: str        # one readable sentence that names the line, the column and the value
    severity: str = 'error'   # 'error': the row is not used; 'warning': it is used or only mentioned
    line: int = 0       # CSV line (the header is line 1); 0 when the issue is not about one line
    column: str = ''
    value: str = ''


def counts(issues):
    errors = sum(1 for i in issues if i.severity == 'error')
    return errors, len(issues) - errors


def first_lines(issues, limit=5):
    """Errors first, then warnings, in file order."""
    ranked = sorted(issues, key=lambda i: (i.severity != 'error', i.line))
    return [i.message for i in ranked[:limit]]


def report_lines(plan_summary, issues):
    errors, warnings = counts(issues)
    lines = [f'# {plan_summary}', f'# {errors} errors (row not used), {warnings} warnings', '']
    ranked = sorted(issues, key=lambda i: (i.severity != 'error', i.line))
    for issue in ranked[:MAX_REPORT_LINES]:
        lines.append(f'[{issue.severity}] {issue.message}')
    if len(ranked) > MAX_REPORT_LINES:
        lines.append(f'... and {len(ranked) - MAX_REPORT_LINES} more')
    return lines


def publish(plan_summary, issues):
    """Remember the issues for the panel and write them to a Text datablock (removed when there are none)."""
    import bpy
    LAST_ISSUES[:] = issues
    text = bpy.data.texts.get(REPORT_TEXT)
    if not issues:
        if text is not None:
            text.clear()
            text.write('# No problems in the last Preview / Replace.\n')
        return
    if text is None:
        text = bpy.data.texts.new(REPORT_TEXT)
    text.clear()
    text.write('\n'.join(report_lines(plan_summary, issues)) + '\n')
