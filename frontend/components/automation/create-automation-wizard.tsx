'use client';

/**
 * Create Automation, in the reference product's four steps: Category,
 * Trigger, Conditions, Review.
 *
 * It used to be a two-field dialog — a name and a trigger from a flat list of
 * nineteen — with everything else on the detail screen. The four steps are
 * not ceremony over that: the trigger is what decides which conditions exist
 * at all, and choosing one from nineteen is a different task from choosing
 * *what kind of thing* this rule is about. Category narrows nineteen to
 * three or four.
 *
 * Conditions are asked for here rather than left to the next screen because
 * a rule with no condition fires on every single record of its trigger, and
 * somebody should see that before it is saved rather than discover it
 * afterwards. Skipping the step is still allowed — the review step says in
 * as many words what "no conditions" means.
 *
 * Actions stay on the detail screen. They are the part that needs the flow
 * canvas, and a rule is created as a *draft*: nothing runs until it is
 * activated there.
 */

import { useState } from 'react';

import { ConditionEditor } from '@/components/automation/condition-editor';
import { StepBar, type WizardStep } from '@/components/classpro/step-bar';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldErrors } from '@/lib/api';
import {
  AUTOMATION_TRIGGER_PATHS,
  createAutomationRule,
  ENQUIRY_STAGE_PATHS,
  updateAutomationRule,
} from '@/lib/automation';
import {
  AUTOMATION_RECORD_LABEL,
  AUTOMATION_RECORD_TRIGGERS,
  AUTOMATION_TRIGGER_LABEL,
  ENQUIRY_STAGE_LABEL,
  ENQUIRY_STAGES,
  type AutomationRecord,
} from '@/lib/labels';
import { cn } from '@/lib/utils';
import type { AutomationCondition, AutomationTrigger } from '@/types/api';

const STEPS: WizardStep[] = [
  { key: 'category', label: 'Category' },
  { key: 'trigger', label: 'Trigger' },
  { key: 'conditions', label: 'Conditions' },
  { key: 'review', label: 'Review' },
];

/** What each category is for, in one line, so the cards are a choice rather
 *  than a list of nouns. */
const CATEGORY_BLURB: Record<AutomationRecord, string> = {
  enquiry: 'On a lead arriving, moving stage, or being edited.',
  activity: 'On a piece of work being completed, or going overdue.',
  form: 'On a form being submitted.',
  class_report: 'On a class report being filed, missed, or flagging a student.',
  student: 'On attendance, an assessment, a risk level, or an overdue project.',
  fee: 'On a payment arriving, or an instalment falling due.',
};

const CATEGORIES = Object.keys(AUTOMATION_RECORD_LABEL) as AutomationRecord[];

export function CreateAutomationWizard({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [step, setStep] = useState('category');
  const [furthest, setFurthest] = useState('category');
  const [category, setCategory] = useState<AutomationRecord | null>(null);
  const [trigger, setTrigger] = useState<AutomationTrigger | null>(null);
  const [conditions, setConditions] = useState<AutomationCondition[]>([]);
  const [name, setName] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  // Reopening is a fresh rule. Reset against a key during render, the
  // convention the other builders in this app use.
  const [openedFor, setOpenedFor] = useState(open);
  if (openedFor !== open) {
    setStep('category');
    setFurthest('category');
    setCategory(null);
    setTrigger(null);
    setConditions([]);
    setName('');
    setErrors({});
    setOpenedFor(open);
  }

  function reach(key: string) {
    setStep(key);
    if (STEPS.findIndex((item) => item.key === key) > STEPS.findIndex((item) => item.key === furthest)) {
      setFurthest(key);
    }
  }

  const triggers = category ? AUTOMATION_RECORD_TRIGGERS[category] : [];
  const stageChoices = ENQUIRY_STAGES.map((stage) => ({
    value: stage,
    label: ENQUIRY_STAGE_LABEL[stage],
  }));

  async function create() {
    if (!trigger) return;
    const label = name.trim();
    if (!label) {
      setErrors({ name: 'Give the automation a name.' });
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      const created = await createAutomationRule({ name: label, trigger });
      if (conditions.length > 0) {
        // Created first, then its conditions: the create endpoint takes the
        // identifying fields only, and a rule with a bad condition should
        // still exist as a draft to fix rather than vanish.
        await updateAutomationRule(created.id, { conditions });
      }
      onCreated(created.id);
    } catch (cause) {
      setErrors(fieldErrors(cause));
    } finally {
      setSaving(false);
    }
  }

  const canGoOn =
    (step === 'category' && category !== null) ||
    (step === 'trigger' && trigger !== null) ||
    step === 'conditions';

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Automation</DialogTitle>
          <DialogDescription>
            Step {STEPS.findIndex((item) => item.key === step) + 1} of {STEPS.length}. It is
            created as a draft — nothing runs until you add its actions and activate it.
          </DialogDescription>
        </DialogHeader>

        <StepBar steps={STEPS} current={step} furthest={furthest} onSelect={reach} />

        {errors.__all__ ? <Alert variant="error">{errors.__all__}</Alert> : null}

        <div className="min-h-[16rem] py-4">
          {step === 'category' ? (
            <div className="space-y-3">
              <p className="text-sm text-ink-muted">What should trigger your automation?</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {CATEGORIES.map((key) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={category === key}
                    onClick={() => {
                      setCategory(key);
                      setTrigger(null);
                      setConditions([]);
                    }}
                    className={cn(
                      'rounded-card border p-4 text-left transition-colors',
                      category === key
                        ? 'border-action bg-selected/40'
                        : 'border-line hover:bg-sunken/60',
                    )}
                  >
                    <span className="block text-sm font-medium">
                      {AUTOMATION_RECORD_LABEL[key]}
                    </span>
                    <span className="mt-1 block text-xs text-ink-muted">
                      {CATEGORY_BLURB[key]}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {step === 'trigger' && category ? (
            <div className="space-y-3">
              <p className="text-sm text-ink-muted">
                Which {AUTOMATION_RECORD_LABEL[category].toLowerCase()} event?
              </p>
              <div className="space-y-2">
                {triggers.map((key) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={trigger === key}
                    onClick={() => {
                      setTrigger(key);
                      setConditions([]);
                    }}
                    className={cn(
                      'block w-full rounded-card border p-3 text-left transition-colors',
                      trigger === key
                        ? 'border-action bg-selected/40'
                        : 'border-line hover:bg-sunken/60',
                    )}
                  >
                    <span className="block text-sm font-medium">
                      {AUTOMATION_TRIGGER_LABEL[key]}
                    </span>
                    <span className="mt-0.5 block text-xs text-ink-muted">
                      {AUTOMATION_TRIGGER_PATHS[key].paths.length} condition
                      {AUTOMATION_TRIGGER_PATHS[key].paths.length === 1 ? '' : 's'} available
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {step === 'conditions' && trigger ? (
            <div className="space-y-3">
              <ConditionEditor
                conditions={conditions}
                triggerMeta={AUTOMATION_TRIGGER_PATHS[trigger]}
                triggerLabel={AUTOMATION_TRIGGER_LABEL[trigger]}
                choicePaths={Object.fromEntries(
                  ENQUIRY_STAGE_PATHS.map((path) => [path, stageChoices]),
                )}
                onChange={setConditions}
              />
            </div>
          ) : null}

          {step === 'review' && trigger && category ? (
            <div className="space-y-4">
              <Field label="Automation name" htmlFor="automation-name" error={errors.name} required>
                <Input
                  id="automation-name"
                  autoFocus
                  value={name}
                  placeholder="Lead allocation"
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <dl className="divide-y divide-line rounded-card border border-line px-3">
                <div className="flex items-center justify-between gap-3 py-2.5">
                  <dt className="text-sm text-ink-muted">Module</dt>
                  <dd className="text-sm">
                    <Badge>{AUTOMATION_RECORD_LABEL[category]}</Badge>
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3 py-2.5">
                  <dt className="text-sm text-ink-muted">Trigger</dt>
                  <dd className="text-sm">{AUTOMATION_TRIGGER_LABEL[trigger]}</dd>
                </div>
                <div className="flex items-center justify-between gap-3 py-2.5">
                  <dt className="text-sm text-ink-muted">Conditions</dt>
                  <dd className="text-sm">{conditions.length}</dd>
                </div>
              </dl>
              {conditions.length === 0 ? (
                <Alert variant="warning">
                  With no conditions this runs for every single{' '}
                  {AUTOMATION_RECORD_LABEL[category].toLowerCase()} that triggers it. That is
                  sometimes exactly right — say, allocating every new lead — and sometimes a
                  surprise, so it is said here rather than discovered later.
                </Alert>
              ) : null}
              <p className="text-sm text-ink-muted">
                Next: its actions, on the automation&rsquo;s own screen. It stays a draft until
                you activate it there.
              </p>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {step !== 'category' ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                const index = STEPS.findIndex((item) => item.key === step);
                setStep(STEPS[index - 1]!.key);
              }}
            >
              Back
            </Button>
          ) : null}
          {step === 'review' ? (
            <Button type="button" disabled={saving} onClick={() => void create()}>
              {saving ? 'Creating…' : 'Create Automation'}
            </Button>
          ) : (
            <Button
              type="button"
              disabled={!canGoOn}
              onClick={() => {
                const index = STEPS.findIndex((item) => item.key === step);
                reach(STEPS[index + 1]!.key);
              }}
            >
              Next
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
