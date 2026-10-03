"use client";

/**
 * The Meritto-style flow builder: a palette of blocks on the left, the rule
 * drawn as a flow of cards in the middle (WHEN → IF → THEN), and a side form
 * on the right for whichever card is selected.
 *
 * Blocks are dragged from the palette onto a drop zone between cards, and
 * cards are dragged to reorder — native HTML drag and drop, no library.
 * Everything drag does is also reachable without a mouse: clicking a block
 * adds it at the end, and each card has move up / move down / remove
 * buttons. The side form docks beside the canvas on a wide screen and slides
 * in as a sheet on a narrow one.
 *
 * The flow is today's rule engine drawn as a flow: one trigger, conditions
 * that must all hold, then actions run in order. Wait and If/else blocks are
 * shown as coming next, never offered as if they worked.
 */

import { useId, useState, type DragEvent, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bell,
  ClipboardCheck,
  ClipboardList,
  Filter,
  GitBranch,
  GripVertical,
  Hourglass,
  ListTodo,
  Mail,
  MessageCircle,
  Trash2,
  UserCog,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";

import {
  ActionRow,
  blankActionFor,
  type ActivityTypeOption,
} from "@/components/automation/action-editor";
import { ConditionRow, newCondition } from "@/components/automation/condition-editor";
import { describeAction, describeCondition } from "@/components/automation/flow-summary";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/hooks/use-media-query";
import type { TriggerPathInfo } from "@/lib/automation";
import { AUTOMATION_ACTION_TYPE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type {
  AutomationAction,
  AutomationActionType,
  AutomationCondition,
  FormField,
  FormFieldOption,
} from "@/types/api";

const MIME = { condition: "application/x-grras-condition", action: "application/x-grras-action" };

type Section = keyof typeof MIME;

type DragPayload =
  | { source: "palette"; actionType?: AutomationActionType }
  | { source: "canvas"; index: number };

export type FlowSelection =
  | { kind: "trigger" }
  | { kind: "condition"; index: number }
  | { kind: "action"; index: number }
  | null;

const ACTION_BLOCKS: { type: AutomationActionType; icon: LucideIcon; hint: string }[] = [
  { type: "create_activity", icon: ListTodo, hint: "A call, demo class or other task, with its content" },
  { type: "update_enquiry", icon: UserCog, hint: "Stage, owner, follow-up date" },
  { type: "assign_form", icon: ClipboardList, hint: "Someone fills in a form" },
  { type: "send_notification", icon: Bell, hint: "An in-app notice, emailed by preference" },
  { type: "send_whatsapp", icon: MessageCircle, hint: "A WhatsApp template" },
  { type: "send_email", icon: Mail, hint: "An email template" },
  { type: "create_review", icon: ClipboardCheck, hint: "A draft performance review" },
  { type: "flag_risk", icon: AlertTriangle, hint: "Mark a student at risk" },
];

const ACTION_ICON: Record<AutomationActionType, LucideIcon> = Object.fromEntries(
  ACTION_BLOCKS.map((block) => [block.type, block.icon]),
) as Record<AutomationActionType, LucideIcon>;

function move<T>(list: T[], from: number, to: number): T[] {
  const copy = list.slice();
  const [item] = copy.splice(from, 1);
  if (item === undefined) return list;
  copy.splice(to > from ? to - 1 : to, 0, item);
  return copy;
}

function insert<T>(list: T[], index: number, item: T): T[] {
  const copy = list.slice();
  copy.splice(index, 0, item);
  return copy;
}

function readPayload(event: DragEvent, section: Section): DragPayload | null {
  try {
    return JSON.parse(event.dataTransfer.getData(MIME[section])) as DragPayload;
  } catch {
    return null;
  }
}

/** A thin gap between cards that opens up when a block of the right kind is
 *  dragged over it. Pointer-only: the keyboard path is the buttons. */
function DropZone({
  section,
  disabled,
  onDrop,
  label,
}: {
  section: Section;
  disabled: boolean;
  onDrop: (payload: DragPayload) => void;
  label?: string;
}) {
  const [over, setOver] = useState(false);
  if (disabled) return <div className="h-2" aria-hidden="true" />;
  return (
    <div
      data-testid={`drop-${section}`}
      aria-hidden="true"
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes(MIME[section])) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const payload = readPayload(event, section);
        if (payload) onDrop(payload);
      }}
      className={cn(
        "flex items-center justify-center rounded-control text-2xs font-medium transition-all",
        over
          ? "my-1 h-10 border-2 border-dashed border-action bg-selected text-selected-fg"
          : label
            ? "my-1 h-10 border border-dashed border-line text-ink-faint"
            : "h-2",
      )}
    >
      {over ? "Drop here" : label ?? null}
    </div>
  );
}

function Connector() {
  return <div className="mx-auto h-5 w-px bg-line-strong" aria-hidden="true" />;
}

function SectionLabel({ children, hint }: { children: ReactNode; hint: string }) {
  return (
    <div className="flex items-baseline gap-2 px-1 pb-1">
      <span className="text-2xs font-bold uppercase tracking-wider text-ink-muted">{children}</span>
      <span className="text-2xs text-ink-faint">{hint}</span>
    </div>
  );
}

/** One card on the canvas: an icon, a kind label, a one-line summary. The
 *  summary is the select button; the small buttons move or remove it. */
function FlowCard({
  icon: Icon,
  kind,
  summary,
  selected,
  tone,
  onSelect,
  drag,
  controls,
}: {
  icon: LucideIcon;
  kind: string;
  summary: string;
  selected: boolean;
  tone: "trigger" | "condition" | "action";
  onSelect: () => void;
  drag?: { section: Section; index: number; disabled: boolean };
  controls?: ReactNode;
}) {
  return (
    <div
      draggable={drag && !drag.disabled ? true : undefined}
      onDragStart={
        drag && !drag.disabled
          ? (event) => {
              const payload: DragPayload = { source: "canvas", index: drag.index };
              event.dataTransfer.setData(MIME[drag.section], JSON.stringify(payload));
              event.dataTransfer.effectAllowed = "move";
            }
          : undefined
      }
      className={cn(
        "group flex items-center gap-2 rounded-card border bg-surface px-2 py-2 shadow-panel transition-colors",
        selected ? "border-action ring-2 ring-action/30" : "border-line hover:border-line-strong",
      )}
    >
      {drag ? (
        <GripVertical
          className={cn("size-4 shrink-0 text-ink-faint", !drag.disabled && "cursor-grab")}
          aria-hidden="true"
        />
      ) : null}
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-control",
          tone === "trigger" && "bg-action text-action-fg",
          tone === "condition" && "bg-info-wash text-info",
          tone === "action" && "bg-success-wash text-success",
        )}
        aria-hidden="true"
      >
        <Icon className="size-4" />
      </span>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="min-w-0 flex-1 rounded-control px-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action"
      >
        <span className="block text-2xs font-semibold uppercase tracking-wide text-ink-faint">{kind}</span>
        <span className="block truncate text-sm text-ink">{summary}</span>
      </button>
      {controls ? <div className="flex shrink-0 items-center gap-0.5">{controls}</div> : null}
    </div>
  );
}

function CardControls({
  label,
  index,
  total,
  disabled,
  onMove,
  onRemove,
}: {
  label: string;
  index: number;
  total: number;
  disabled: boolean;
  onMove: (to: number) => void;
  onRemove: () => void;
}) {
  if (disabled) return null;
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label={`Move ${label} up`}
        disabled={index === 0}
        onClick={() => onMove(index - 1)}
      >
        <ArrowUp className="size-3.5" aria-hidden="true" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label={`Move ${label} down`}
        disabled={index === total - 1}
        onClick={() => onMove(index + 2)}
      >
        <ArrowDown className="size-3.5" aria-hidden="true" />
      </Button>
      <Button type="button" variant="ghost" size="sm" aria-label={`Remove ${label}`} onClick={onRemove}>
        <Trash2 className="size-3.5" aria-hidden="true" />
      </Button>
    </>
  );
}

function PaletteBlock({
  icon: Icon,
  label,
  hint,
  section,
  payload,
  disabled,
  onAdd,
}: {
  icon: LucideIcon;
  label: string;
  hint: string;
  section: Section;
  payload: DragPayload;
  disabled: boolean;
  onAdd: () => void;
}) {
  return (
    <button
      type="button"
      draggable={!disabled}
      disabled={disabled}
      onDragStart={(event) => {
        event.dataTransfer.setData(MIME[section], JSON.stringify(payload));
        event.dataTransfer.effectAllowed = "copy";
      }}
      onClick={onAdd}
      title={`Drag onto the flow, or click to add “${label}” at the end`}
      className={cn(
        "flex w-full items-start gap-2 rounded-control border border-line bg-surface px-2 py-1.5 text-left",
        "hover:border-line-strong hover:bg-sunken/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-action",
        !disabled && "cursor-grab",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-ink-muted" aria-hidden="true" />
      <span className="min-w-0">
        <span className="block text-xs font-medium text-ink">{label}</span>
        <span className="block text-2xs leading-snug text-ink-faint">{hint}</span>
      </span>
    </button>
  );
}

export function FlowBuilder({
  triggerKind,
  triggerSummary,
  renderTriggerForm,
  conditions,
  onConditionsChange,
  actions,
  onActionsChange,
  triggerMeta,
  formFields,
  choicePaths,
  activityTypeOptions,
  formOptions,
  variables,
  disabled = false,
}: {
  /** "Enquiry · Created" — the record and its event. */
  triggerKind: string;
  /** A second line under it, e.g. which form. */
  triggerSummary: string;
  renderTriggerForm: () => ReactNode;
  conditions: AutomationCondition[];
  onConditionsChange: (next: AutomationCondition[]) => void;
  actions: AutomationAction[];
  onActionsChange: (next: AutomationAction[]) => void;
  triggerMeta: TriggerPathInfo;
  formFields: FormField[];
  choicePaths: Record<string, FormFieldOption[]>;
  activityTypeOptions: ActivityTypeOption[];
  formOptions: { slug: string; name: string }[];
  variables: string[];
  disabled?: boolean;
}) {
  const uid = useId();
  const docked = useMediaQuery("(min-width: 1024px)");
  const [selection, setSelection] = useState<FlowSelection>(null);
  const lookups = { activityTypes: activityTypeOptions, forms: formOptions, formFields };

  // A selection pointing past the end (the list shrank from outside, e.g. a
  // trigger change cleared the conditions) selects nothing.
  const selected: FlowSelection =
    selection?.kind === "condition" && !conditions[selection.index]
      ? null
      : selection?.kind === "action" && !actions[selection.index]
        ? null
        : selection;

  function addCondition(at = conditions.length) {
    onConditionsChange(insert(conditions, at, newCondition(formFields, triggerMeta.paths)));
    setSelection({ kind: "condition", index: at });
  }

  function addAction(type: AutomationActionType, at = actions.length) {
    onActionsChange(insert(actions, at, blankActionFor(type)));
    setSelection({ kind: "action", index: at });
  }

  function dropCondition(payload: DragPayload, at: number) {
    if (payload.source === "palette") {
      addCondition(at);
    } else {
      onConditionsChange(move(conditions, payload.index, at));
      setSelection({ kind: "condition", index: at > payload.index ? at - 1 : at });
    }
  }

  function dropAction(payload: DragPayload, at: number) {
    if (payload.source === "palette") {
      if (payload.actionType) addAction(payload.actionType, at);
    } else {
      onActionsChange(move(actions, payload.index, at));
      setSelection({ kind: "action", index: at > payload.index ? at - 1 : at });
    }
  }

  function moveCondition(from: number, to: number) {
    onConditionsChange(move(conditions, from, to));
    setSelection({ kind: "condition", index: to > from ? to - 1 : to });
  }

  function moveAction(from: number, to: number) {
    onActionsChange(move(actions, from, to));
    setSelection({ kind: "action", index: to > from ? to - 1 : to });
  }

  function removeCondition(index: number) {
    onConditionsChange(conditions.filter((_, i) => i !== index));
    setSelection(null);
  }

  function removeAction(index: number) {
    onActionsChange(actions.filter((_, i) => i !== index));
    setSelection(null);
  }

  // --- The side form ---------------------------------------------------
  let panelTitle = "";
  let panelBody: ReactNode = null;
  if (selected?.kind === "trigger") {
    panelTitle = "When";
    panelBody = renderTriggerForm();
  } else if (selected?.kind === "condition") {
    const condition = conditions[selected.index]!;
    panelTitle = `Condition ${selected.index + 1}`;
    panelBody = (
      <ConditionRow
        condition={condition}
        triggerMeta={triggerMeta}
        formFields={formFields}
        choicePaths={choicePaths}
        disabled={disabled}
        onChange={(next) => {
          const copy = conditions.slice();
          copy[selected.index] = next;
          onConditionsChange(copy);
        }}
        onRemove={() => removeCondition(selected.index)}
      />
    );
  } else if (selected?.kind === "action") {
    const action = actions[selected.index]!;
    panelTitle = `Step ${selected.index + 1}: ${AUTOMATION_ACTION_TYPE_LABEL[action.type]}`;
    panelBody = (
      <ActionRow
        action={action}
        activityTypeOptions={activityTypeOptions}
        formOptions={formOptions}
        variables={variables}
        disabled={disabled}
        onChange={(next) => {
          const copy = actions.slice();
          copy[selected.index] = next;
          onActionsChange(copy);
        }}
        onRemove={() => removeAction(selected.index)}
      />
    );
  }

  const panel = (
    <div className="space-y-4">
      <p className="text-xs text-ink-muted">
        Changes apply to the flow straight away; save the rule to keep them.
      </p>
      {panelBody}
    </div>
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[13rem_minmax(0,1fr)_24rem]">
      {/* --- Palette ------------------------------------------------------ */}
      <aside aria-label="Blocks" className="space-y-4">
        <div className="space-y-1.5">
          <p className="px-1 text-2xs font-bold uppercase tracking-wider text-ink-muted">Check</p>
          <PaletteBlock
            icon={Filter}
            label="Condition"
            hint="Only go on when this is true"
            section="condition"
            payload={{ source: "palette" }}
            disabled={disabled}
            onAdd={() => addCondition()}
          />
        </div>
        <div className="space-y-1.5">
          <p className="px-1 text-2xs font-bold uppercase tracking-wider text-ink-muted">Do</p>
          {ACTION_BLOCKS.map((block) => (
            <PaletteBlock
              key={block.type}
              icon={block.icon}
              label={AUTOMATION_ACTION_TYPE_LABEL[block.type]}
              hint={block.hint}
              section="action"
              payload={{ source: "palette", actionType: block.type }}
              disabled={disabled}
              onAdd={() => addAction(block.type)}
            />
          ))}
        </div>
        <div className="space-y-1.5">
          <p className="px-1 text-2xs font-bold uppercase tracking-wider text-ink-muted">
            Coming next
          </p>
          {[
            { icon: Hourglass, label: "Wait", hint: "Pause for a time, or until something happens" },
            { icon: GitBranch, label: "If / else", hint: "Split into a Yes and a No path" },
          ].map((block) => (
            <div
              key={block.label}
              aria-disabled="true"
              className="flex items-start gap-2 rounded-control border border-dashed border-line px-2 py-1.5 opacity-70"
            >
              <block.icon className="mt-0.5 size-4 shrink-0 text-ink-faint" aria-hidden="true" />
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 text-xs font-medium text-ink-muted">
                  {block.label}
                  <Badge variant="neutral" dot={false}>
                    Soon
                  </Badge>
                </span>
                <span className="block text-2xs leading-snug text-ink-faint">{block.hint}</span>
              </span>
            </div>
          ))}
        </div>
      </aside>

      {/* --- Canvas ------------------------------------------------------- */}
      <section
        aria-label="Flow"
        className="min-w-0 rounded-panel border border-line bg-sunken/50 p-4 [background-image:radial-gradient(var(--color-line)_1px,transparent_1px)] [background-size:16px_16px]"
      >
        <div className="mx-auto max-w-xl">
          <SectionLabel hint="what starts it">When</SectionLabel>
          <FlowCard
            icon={Zap}
            kind={triggerKind}
            summary={triggerSummary}
            tone="trigger"
            selected={selected?.kind === "trigger"}
            onSelect={() => setSelection({ kind: "trigger" })}
          />
          <Connector />

          <SectionLabel hint="all must be true">If</SectionLabel>
          <ol className="space-y-0" aria-label="Conditions">
            {conditions.length === 0 ? (
              <li>
                <DropZone
                  section="condition"
                  disabled={disabled}
                  label="No conditions: runs every time. Drop a condition here."
                  onDrop={(payload) => dropCondition(payload, 0)}
                />
              </li>
            ) : (
              conditions.map((condition, index) => (
                <li key={`${uid}-c-${index}`}>
                  <DropZone
                    section="condition"
                    disabled={disabled}
                    onDrop={(payload) => dropCondition(payload, index)}
                  />
                  <FlowCard
                    icon={Filter}
                    kind={index === 0 ? "If" : "And"}
                    summary={describeCondition(condition, formFields)}
                    tone="condition"
                    selected={selected?.kind === "condition" && selected.index === index}
                    onSelect={() => setSelection({ kind: "condition", index })}
                    drag={{ section: "condition", index, disabled }}
                    controls={
                      <CardControls
                        label={`condition ${index + 1}`}
                        index={index}
                        total={conditions.length}
                        disabled={disabled}
                        onMove={(to) => moveCondition(index, to)}
                        onRemove={() => removeCondition(index)}
                      />
                    }
                  />
                  {index === conditions.length - 1 ? (
                    <DropZone
                      section="condition"
                      disabled={disabled}
                      onDrop={(payload) => dropCondition(payload, conditions.length)}
                    />
                  ) : null}
                </li>
              ))
            )}
          </ol>
          {!disabled ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-1"
              onClick={() => addCondition()}
            >
              + Add condition
            </Button>
          ) : null}
          <Connector />

          <SectionLabel hint="in this order">Then</SectionLabel>
          <ol className="space-y-0" aria-label="Actions">
            {actions.length === 0 ? (
              <li>
                <DropZone
                  section="action"
                  disabled={disabled}
                  label="Nothing happens yet. Drop an action here."
                  onDrop={(payload) => dropAction(payload, 0)}
                />
              </li>
            ) : (
              actions.map((action, index) => (
                <li key={`${uid}-a-${index}`}>
                  <DropZone
                    section="action"
                    disabled={disabled}
                    onDrop={(payload) => dropAction(payload, index)}
                  />
                  <FlowCard
                    icon={ACTION_ICON[action.type] ?? ListTodo}
                    kind={`${index + 1}. ${AUTOMATION_ACTION_TYPE_LABEL[action.type]}`}
                    summary={describeAction(action, lookups)}
                    tone="action"
                    selected={selected?.kind === "action" && selected.index === index}
                    onSelect={() => setSelection({ kind: "action", index })}
                    drag={{ section: "action", index, disabled }}
                    controls={
                      <CardControls
                        label={`step ${index + 1}`}
                        index={index}
                        total={actions.length}
                        disabled={disabled}
                        onMove={(to) => moveAction(index, to)}
                        onRemove={() => removeAction(index)}
                      />
                    }
                  />
                  {index === actions.length - 1 ? (
                    <DropZone
                      section="action"
                      disabled={disabled}
                      onDrop={(payload) => dropAction(payload, actions.length)}
                    />
                  ) : null}
                </li>
              ))
            )}
          </ol>
          {!disabled ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-1"
              onClick={() => addAction("create_activity")}
            >
              + Add action
            </Button>
          ) : null}
          <Connector />
          <div className="mx-auto w-fit rounded-pill border border-line bg-surface px-3 py-1 text-2xs font-semibold uppercase tracking-wider text-ink-faint">
            End
          </div>
        </div>
      </section>

      {/* --- Side form ---------------------------------------------------- */}
      {docked ? (
        <aside
          aria-label="Selected step"
          className="self-start rounded-panel border border-line bg-surface p-4 shadow-panel lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto"
        >
          {selected ? (
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">{panelTitle}</h3>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label="Close the side form"
                  onClick={() => setSelection(null)}
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </div>
              {panel}
            </div>
          ) : (
            <p className="text-sm text-ink-muted">
              Select a card to edit it here, or drag a block from the left onto the flow.
            </p>
          )}
        </aside>
      ) : (
        <Sheet open={selected !== null} onOpenChange={(open) => (open ? undefined : setSelection(null))}>
          <SheetContent size="lg" className="overflow-y-auto">
            <SheetHeader>
              <SheetTitle>{panelTitle}</SheetTitle>
            </SheetHeader>
            <div className="mt-4">{panel}</div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
