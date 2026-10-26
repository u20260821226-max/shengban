"""Conservative removal of dark screenshot chrome, keeping the full paper width."""
from PIL import Image, ImageFilter


def paper_bounds(gray):
    width, height = gray.size
    # Average over the width and smooth thin staff lines so they cannot split a page.
    rows = list(gray.resize((1, height), Image.Resampling.BOX)
                .filter(ImageFilter.BoxBlur(8)).getdata())
    runs, start = [], None
    for y, light in enumerate(rows + [0]):
        if light > 150 and start is None:
            start = y
        elif light <= 150 and start is not None:
            runs.append((start, y)); start = None
    if not runs:
        return None
    top, bottom = max(runs, key=lambda span: span[1] - span[0])
    if bottom - top < max(400, height * .4):
        return None
    # Only trim substantial dark bands. White scan margins must remain intact.
    outside = rows[:max(0, top - 12)] + rows[min(height, bottom + 12):]
    if not outside or sum(outside) / len(outside) > 65:
        return None
    if top < height * .05 and bottom > height * .95:
        return None
    return (0, max(0, top - 3), width, min(height, bottom + 3))
