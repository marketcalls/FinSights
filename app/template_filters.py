"""
Custom Jinja2 template filters for content formatting.
"""
import re
import markdown
import bleach
from markupsafe import Markup
from datetime import datetime


# Allowed HTML tags and attributes for sanitization
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'blockquote', 'pre', 'code',
    'a', 'span', 'div',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'hr',
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target', 'rel'],
    'span': ['class'],
    'div': ['class'],
    'code': ['class'],
    'pre': ['class'],
    '*': ['class'],
}


def render_markdown(text: str) -> Markup:
    """
    Convert markdown text to sanitized HTML.
    Returns a Markup object so Jinja2 knows it's safe.
    """
    if not text:
        return Markup('')

    # Convert markdown to HTML
    md = markdown.Markdown(
        extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.tables',
            'markdown.extensions.nl2br',
            'markdown.extensions.sane_lists',
        ]
    )
    html = md.convert(text)

    # Sanitize HTML to prevent XSS
    clean_html = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True
    )

    # Add target="_blank" and rel="noopener" to links
    clean_html = re.sub(
        r'<a href="([^"]*)"',
        r'<a href="\1" target="_blank" rel="noopener noreferrer"',
        clean_html
    )

    return Markup(clean_html)


def smart_truncate(text: str, length: int = 150, suffix: str = '...') -> str:
    """
    Truncate text at word boundary, respecting sentence structure.
    """
    if not text:
        return ''

    # Clean up whitespace
    text = ' '.join(text.split())

    if len(text) <= length:
        return text

    # Find a good break point
    truncated = text[:length]

    # Try to break at sentence end
    sentence_ends = ['.', '!', '?']
    for i in range(len(truncated) - 1, max(length - 50, 0), -1):
        if truncated[i] in sentence_ends:
            return truncated[:i + 1]

    # Otherwise break at word boundary
    last_space = truncated.rfind(' ')
    if last_space > length - 50:
        return truncated[:last_space] + suffix

    return truncated + suffix


def format_date(date_str: str, format_type: str = 'short') -> str:
    """
    Format a date string for display.
    format_type: 'short' (29 Nov), 'medium' (29 Nov 2025), 'long' (November 29, 2025), 'relative' (2 days ago)
    """
    if not date_str:
        return ''

    try:
        # Parse ISO format datetime
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')

        now = datetime.now()

        if format_type == 'relative':
            diff = now - dt.replace(tzinfo=None)
            days = diff.days
            hours = diff.seconds // 3600

            if days == 0:
                if hours == 0:
                    return 'Just now'
                elif hours == 1:
                    return '1 hour ago'
                else:
                    return f'{hours} hours ago'
            elif days == 1:
                return 'Yesterday'
            elif days < 7:
                return f'{days} days ago'
            elif days < 30:
                weeks = days // 7
                return f'{weeks} week{"s" if weeks > 1 else ""} ago'
            else:
                return dt.strftime('%d %b %Y')

        elif format_type == 'short':
            return dt.strftime('%d %b')
        elif format_type == 'medium':
            return dt.strftime('%d %b %Y')
        elif format_type == 'long':
            return dt.strftime('%B %d, %Y')
        elif format_type == 'time':
            return dt.strftime('%d %b %Y, %H:%M')
        else:
            return dt.strftime('%d %b %Y')

    except Exception:
        # Return first 10 chars if parsing fails
        return date_str[:10] if len(date_str) >= 10 else date_str


def format_summary(text: str, max_length: int = 200) -> str:
    """
    Format a summary for card display - clean markdown, truncate smartly.
    """
    if not text:
        return ''

    # Remove markdown syntax for preview
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Remove links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bullet points
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    # Remove numbered lists
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Clean up multiple spaces/newlines
    text = ' '.join(text.split())

    return smart_truncate(text, max_length)


def extract_key_points(content: str, max_points: int = 5) -> list:
    """
    Extract key bullet points from content for summary display.
    """
    if not content:
        return []

    points = []

    # Look for existing bullet points
    bullet_pattern = r'^\s*[-*+]\s+(.+)$'
    matches = re.findall(bullet_pattern, content, re.MULTILINE)

    if matches:
        for match in matches[:max_points]:
            point = match.strip()
            if len(point) > 10:  # Skip very short points
                points.append(smart_truncate(point, 150))

    # If no bullets found, try to extract from paragraphs
    if not points:
        # Split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', content)
        for sentence in sentences[:max_points]:
            sentence = sentence.strip()
            if len(sentence) > 20:  # Skip very short sentences
                points.append(smart_truncate(sentence, 150))

    return points


def highlight_search(text: str, query: str) -> Markup:
    """
    Highlight search terms in text.
    """
    if not text or not query:
        return Markup(text or '')

    # Escape HTML first
    text = bleach.clean(text, tags=[], strip=True)

    # Case-insensitive highlight
    pattern = re.compile(f'({re.escape(query)})', re.IGNORECASE)
    highlighted = pattern.sub(r'<mark class="bg-yellow-200 px-0.5 rounded">\1</mark>', text)

    return Markup(highlighted)


def sentiment_badge(score: int, show_label: bool = True) -> Markup:
    """
    Generate a color-coded sentiment badge.
    Score ranges from -10 (extremely negative) to +10 (extremely positive).
    """
    if score is None:
        return Markup('')

    # Determine color based on score
    if score >= 7:
        bg_class = "bg-green-500"
        text_class = "text-white"
        label = "Very Positive"
    elif score >= 4:
        bg_class = "bg-green-400"
        text_class = "text-white"
        label = "Positive"
    elif score >= 1:
        bg_class = "bg-green-300"
        text_class = "text-green-900"
        label = "Slightly Positive"
    elif score == 0:
        bg_class = "bg-gray-400"
        text_class = "text-white"
        label = "Neutral"
    elif score >= -3:
        bg_class = "bg-red-300"
        text_class = "text-red-900"
        label = "Slightly Negative"
    elif score >= -6:
        bg_class = "bg-red-400"
        text_class = "text-white"
        label = "Negative"
    else:
        bg_class = "bg-red-500"
        text_class = "text-white"
        label = "Very Negative"

    # Format score with sign
    score_str = f"+{score}" if score > 0 else str(score)

    if show_label:
        html = f'<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium {bg_class} {text_class}">{score_str} {label}</span>'
    else:
        html = f'<span class="inline-flex items-center justify-center w-8 h-5 rounded-full text-xs font-bold {bg_class} {text_class}">{score_str}</span>'

    return Markup(html)


def sentiment_color(score: int) -> str:
    """
    Return just the color class for a sentiment score.
    Useful for custom styling.
    """
    if score is None:
        return "text-gray-400"

    if score >= 7:
        return "text-green-500"
    elif score >= 4:
        return "text-green-400"
    elif score >= 1:
        return "text-green-300"
    elif score == 0:
        return "text-gray-400"
    elif score >= -3:
        return "text-red-300"
    elif score >= -6:
        return "text-red-400"
    else:
        return "text-red-500"


def register_filters(templates):
    """
    Register all custom filters with the Jinja2 environment.
    Works with FastAPI's Jinja2Templates object.
    """
    templates.env.filters['markdown'] = render_markdown
    templates.env.filters['smart_truncate'] = smart_truncate
    templates.env.filters['format_date'] = format_date
    templates.env.filters['format_summary'] = format_summary
    templates.env.filters['extract_key_points'] = extract_key_points
    templates.env.filters['highlight_search'] = highlight_search
    templates.env.filters['sentiment_badge'] = sentiment_badge
    templates.env.filters['sentiment_color'] = sentiment_color

    # Add globals for templates
    templates.env.globals['now'] = datetime.now
