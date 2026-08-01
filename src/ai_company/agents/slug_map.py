"""Slug assignment and collision detection for company persona agents.

Executives use an explicit title -> slug table (their titles are too long
for @-mention ergonomics, e.g. ``Chief Executive Officer`` -> ``ceo``).
Specialists and board members are slugified from their expertise/role.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Explicit slug for every executive title. These are the @-mention names.
EXECUTIVE_SLUGS: dict[str, str] = {
    "Chief Executive Officer": "ceo",
    "Chief Technology Officer": "cto",
    "Chief Financial Officer": "cfo",
    "Chief Operating Officer": "coo",
    "Chief Marketing Officer": "cmo",
    "Chief AI Officer": "caio",
    "Chief Human Resources Officer": "chro",
    "Chief Legal Officer": "clo",
    "Chief Information Security Officer": "ciso",
    "Chief Information Officer": "cio",
    "Chief Data Officer": "cdo",
    "Chief Strategy Officer": "cso",
    "Chief of Staff": "chief-of-staff",
}

# Built-in opencode agent names that persona slugs must never shadow.
BUILTIN_AGENT_SLUGS: tuple[str, ...] = (
    "build",
    "plan",
    "explore",
    "general",
    "architect",
    "builder",
    "compaction",
    "title",
    "summary",
)


def slugify(title_or_name: str) -> str:
    """Convert a title or name into a lowercase hyphenated slug.

    Only alphanumeric characters are kept; every other character (spaces,
    dots, ampersands, parentheses, ...) becomes a hyphen, and runs of
    separators collapse into a single hyphen.
    """
    text = title_or_name.strip().lower()
    parts: list[str] = []
    prev_sep = False
    for ch in text:
        if ch.isalnum():
            parts.append(ch)
            prev_sep = False
        elif not prev_sep:
            parts.append("-")
            prev_sep = True
    slug = "".join(parts).strip("-")
    return slug


class AgentSlugCollisionError(ValueError):
    """Raised when two personas resolve to the same slug or a reserved name."""


class AgentSlugItem(BaseModel):
    """A single persona participating in slug assignment.

    ``title`` is the executive title, specialist expertise, or board role.
    """

    name: str
    title: str = ""
    role: str = ""

    @property
    def display_title(self) -> str:
        """The best available descriptor for this persona."""
        return self.title or self.role or self.name


class AgentSlugIndex(BaseModel):
    """Assigns deterministic slugs and detects collisions across personas.

    Slugs are assigned in item order: an explicit executive slug when the
    title is a known executive title, otherwise ``slugify(title)``, then
    ``slugify(role)``, then ``slugify(name)``.

    Two different people whose titles/roles resolve to the same base slug
    (e.g. two board members both titled ``Non-Executive Director``) are
    disambiguated deterministically by appending the slugified name of the
    later person (``non-executive-director-amara-okafor``). Genuine
    duplicates — the same name claiming the same base slug more than once —
    and slugs that shadow a built-in opencode agent are reported as
    collisions and raise :class:`AgentSlugCollisionError`.
    """

    items: list[AgentSlugItem] = Field(default_factory=list)
    reserved_slugs: tuple[str, ...] = BUILTIN_AGENT_SLUGS

    def slug_for(self, item: AgentSlugItem) -> str:
        """Resolve the base slug for a single item."""
        if item.title in EXECUTIVE_SLUGS:
            return EXECUTIVE_SLUGS[item.title]
        if item.title:
            return slugify(item.title)
        if item.role:
            return slugify(item.role)
        return slugify(item.name)

    def _assign(self) -> list[tuple[AgentSlugItem, str]]:
        """Return deterministic ``(item, slug)`` pairs.

        Different people sharing a base slug receive a name-based suffix;
        reserved slugs and true duplicates are left untouched so they can
        be reported by :meth:`collisions`.
        """
        taken: dict[str, str] = {}
        pairs: list[tuple[AgentSlugItem, str]] = []
        for item in self.items:
            base = self.slug_for(item)
            if not base or base in self.reserved_slugs:
                pairs.append((item, base))
                continue
            owner = taken.get(base)
            if owner is None:
                pairs.append((item, base))
                taken[base] = item.name
                continue
            if owner == item.name:
                # The same persona appears again — report as a duplicate.
                pairs.append((item, base))
                continue
            candidate = f"{base}-{slugify(item.name)}"
            n = 2
            while candidate in taken:
                candidate = f"{base}-{slugify(item.name)}-{n}"
                n += 1
            pairs.append((item, candidate))
            taken[candidate] = item.name
        return pairs

    def resolved_slugs(self) -> list[str]:
        """Return the final slug for every item, in deterministic item order."""
        return [slug for _, slug in self._assign()]

    def collisions(self) -> list[str]:
        """Return human-readable descriptions of every slug collision.

        A collision is a slug that shadows a built-in opencode agent, an
        empty slug, or the same persona (same name + base slug) appearing
        more than once.
        """
        messages: list[str] = []
        for item, slug in self._assign():
            if not slug:
                messages.append(
                    f'  - "{item.name}" resolves to an empty slug — '
                    "give it a title, role, or non-empty name"
                )
            elif slug in self.reserved_slugs:
                messages.append(
                    f'  - slug "{slug}" for "{item.name}" collides with a '
                    "built-in opencode agent name — rename the persona"
                )
        base_counts: dict[tuple[str, str], int] = {}
        for item in self.items:
            base = self.slug_for(item)
            if base:
                key = (item.name, base)
                base_counts[key] = base_counts.get(key, 0) + 1
        for (name, base), count in sorted(base_counts.items()):
            if count > 1:
                messages.append(
                    f'  - slug "{base}" is assigned to "{name}" {count} '
                    "times — duplicate persona entry"
                )
        return messages

    def raise_for_collisions(self) -> None:
        """Raise :class:`AgentSlugCollisionError` when any collision exists."""
        messages = self.collisions()
        if messages:
            raise AgentSlugCollisionError(
                "Agent slug collisions detected:\n" + "\n".join(messages)
            )
