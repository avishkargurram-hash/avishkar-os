# Contributing

Avishkar OS is the shared foundation for every Avishkar Labs product.
Changes here have blast radius across all of them — this document exists
so that blast radius is always deliberate.

## Before you write code

1. **Read [CLAUDE.md](./CLAUDE.md)** if you're an AI agent working in this
   repo — it's loaded automatically by Claude Code, but read it explicitly
   if you're not sure it's in context.
2. **Ask the seven questions** from CLAUDE.md's mission section: why does
   this exist, can it be reused, can it become a factory, can it be
   automated, does it belong in Avishkar OS (vs. a product repo), is the
   architecture scalable, what would a Staff Engineer do.
3. **Check [ARCHITECTURE.md](./ARCHITECTURE.md)** for where the change
   belongs — especially the Factories vs. Library split (§2). A change
   that doesn't fit either cleanly probably needs an ADR before code.
4. **If the change alters structure, dependency direction, or introduces a
   new top-level concept** (a new factory, a new library shelf, a new
   cross-cutting module): write the ADR in [DECISIONS.md](./DECISIONS.md)
   first, get it accepted, then build.

## Making the change

- Follow [STANDARDS.md](./STANDARDS.md) — naming, the mandatory module
  README template, testing/eval expectations, security checklist.
- New module → new README using the template in STANDARDS.md §2, with an
  honest Purpose section. If you can't write that section truthfully, the
  module isn't ready to exist.
- Keep commits scoped to one logical change. State *what* changed and,
  where it isn't obvious from the diff, *why*.
- No generated `__pycache__`, `node_modules`, `.env`, or other local
  artifacts — check `.gitignore` covers what you're producing before
  committing.

## Review checklist (what a reviewer checks)

- [ ] Does this belong in Avishkar OS, or is it product logic that leaked
      in? (ARCHITECTURE.md §1)
- [ ] If it's in `factories/`, is it a generator — not one-off output?
      If it's in a library shelf, is it hardened, reusable output — not
      generator code? (ARCHITECTURE.md §2)
- [ ] Does the module README follow the template and tell the truth,
      including its Limitations?
- [ ] Does it respect the dependency direction in ARCHITECTURE.md §5
      (`core/` depends on nothing internal; nothing internal depends on
      an application)?
- [ ] Are secrets/credentials absent from the diff?
- [ ] If this is a new agent: could an existing Chief Domain Agent have
      absorbed this as a role instead of becoming a new agent?
      (ARCHITECTURE.md §4)
- [ ] Structural changes: is there an accepted ADR?

## Proposing a new factory

A new factory is a significant, permanent addition — it's a promise that
this *kind* of thing will be built repeatedly across products. Before
proposing one:

1. Confirm the capability doesn't already fit inside an existing factory's
   scope.
2. Write the ADR: what it produces, where the output lands (or why it has
   no top-level shelf — see ARCHITECTURE.md §2), and what it depends on.
3. Get it accepted before scaffolding `factories/<name>-factory/`.

## Questions

If something in this repo's structure or rules seems wrong for a real
change you're trying to make, don't route around it — raise it. Challenging
weak design is the expected default here, not an exception.
