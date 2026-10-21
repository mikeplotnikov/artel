# Route O templates

All files live in `work/onboarding/` of the project. Owner-facing text is in the owner's language
(`~/.artel/artel.toml` → `owner.languages.human_docs`); file names and keys stay English.

## intake.md (O0)

```markdown
# Intake — <project> — <date>
- What it is (one line):
- Stage: in production since … / not yet in production
- In flight (owner's words): …
- No-go areas (do not touch): …
- Discovery exclusions (never read): …
- Production operations agents perform today → keep without asking? (yes/no per operation): …
- Owner's expected profile (the snapshot proposes one in O1; confirmed at the gate): …
- Emergency containment approved (O0.5): yes/no
```

## state-report.md (O2a) — one page, plain language

```markdown
# Состояние проекта <name> на <as_of: date, commit>
## Что работает в проде
- … (evidence: release tag / deploy run / commit)
## Что сделано и не выкачено
- …
## Что в работе
| Что | Где (ветка/PR/worktree) | Состояние | Ближайшая безопасная граница |
## Что впереди по планам проекта
- Утверждённые спецификации и их срезы: …
- Дорожная карта / приоритеты бэклога: …
## Где документы расходятся с фактами
| Документ:строка | Пишет | Факт (locator) |
## Риски, найденные при разборе (кратко; детали — в audit.md)
```

## confirmation questions (O2a)

Batches of 3–4, each answerable in a line; record every answer in `approvals.md`:
"Приоритет сейчас — X, а не Y?", "Пункт бэклога Z ещё актуален?", "Ветка W жива или её можно закрыть?".

## plan-review.md (O2b)

```markdown
# Пересмотр плана — <project> — <date>
| Пункт прежнего плана | Источник | Вердикт (оставить/скорректировать/добавить/закрыть) | Почему | Доказательство |
## Добавления, которых требует артель
| Что | Зачем | Уровень риска |
```

## in-flight ledger (part of the gate)

| Item (branch / worktree / feature) | Has approved spec? | Mid-review-wave? | Disposition (adopt as is / spec from reality / finish wave then switch / close) | Next safe boundary |

## approvals.md entry

```markdown
## <date time> — <gate name>
- Approved scope: …
- Owner's words: "…"
- Open items accepted: …
- Rejected / returned with reasons: …
```

## STATE.md (resume pointer, rewritten at every stage, ≤ 4 KB)

```markdown
# Onboarding — <project>
- Route: O · Stage: O2b        (O0 | O0.5 | O1 | O2 | O2a | O2b | gate | O3 | O4 | O5 | O6 | O7)
- Status: active              (active | done — the `artel` entry resumes onboarding until done)
- Snapshot: work/onboarding/snapshot.json · as_of <sha> · proposed profile <light|standard|critical>
- Gate: pending | approved <date> | rejected <date> → back to <stage>
- Open owner questions: …
- Next: <one line>
```
