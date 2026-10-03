/**
 * The Meritto-style flow builder: blocks dragged from the palette land where
 * they are dropped, cards drag to reorder, the same moves work from buttons,
 * a card opens its side form, and each card says what it will do.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { FlowBuilder } from "@/components/automation/flow-builder";
import { AUTOMATION_TRIGGER_PATHS } from "@/lib/automation";
import type { AutomationAction, AutomationCondition } from "@/types/api";

vi.mock("@/components/automation/use-published-fields", () => ({
  usePublishedFields: () => [],
}));

/** A stand-in for the browser's DataTransfer, which jsdom does not have. */
function dataTransfer() {
  const data: Record<string, string> = {};
  return {
    data,
    types: [] as string[],
    effectAllowed: "",
    dropEffect: "",
    setData(type: string, value: string) {
      data[type] = value;
      this.types.push(type);
    },
    getData(type: string) {
      return data[type] ?? "";
    },
  };
}

const CALL: AutomationAction = {
  type: "create_activity",
  params: { type: "enquiry-call", assign_to: "enquiry_owner", due_in_hours: 2 },
};
const STAGE: AutomationAction = {
  type: "update_enquiry",
  params: { stage: "contacted", owner: "" },
};

function Harness({
  initialActions = [CALL, STAGE],
  initialConditions = [],
}: {
  initialActions?: AutomationAction[];
  initialConditions?: AutomationCondition[];
}) {
  const [actions, setActions] = useState(initialActions);
  const [conditions, setConditions] = useState(initialConditions);
  return (
    <>
      <FlowBuilder
        triggerKind="When · Enquiry"
        triggerSummary="Created"
        renderTriggerForm={() => <p>Trigger form</p>}
        conditions={conditions}
        onConditionsChange={setConditions}
        actions={actions}
        onActionsChange={setActions}
        triggerMeta={AUTOMATION_TRIGGER_PATHS.ENQUIRY_CREATED}
        formFields={[]}
        choicePaths={{}}
        activityTypeOptions={[
          { slug: "enquiry-call", name: "Counselling call", subject: "enquiry", form: null },
        ]}
        formOptions={[]}
        variables={["enquiry.full_name"]}
      />
      <output data-testid="actions">{JSON.stringify(actions.map((action) => action.type))}</output>
      <output data-testid="conditions">{JSON.stringify(conditions.map((c) => c.path))}</output>
    </>
  );
}

function actionTypes(): string[] {
  return JSON.parse(screen.getByTestId("actions").textContent ?? "[]");
}

describe("FlowBuilder", () => {
  it("draws each step with a plain summary", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: /1\. Create an activity\s*Counselling call → the enquiry's owner, due in 2 h/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /2\. Update the enquiry\s*stage → Contacted/ })).toBeInTheDocument();
    // Coming-next blocks are shown but never offered.
    expect(screen.getByText("Wait")).toBeInTheDocument();
    expect(screen.getByText("If / else")).toBeInTheDocument();
  });

  it("drops a palette block where it is released", () => {
    render(<Harness />);
    const transfer = dataTransfer();
    fireEvent.dragStart(screen.getByRole("button", { name: /Send a form to fill/ }), {
      dataTransfer: transfer,
    });
    // The drop zone above step 1.
    const zones = screen.getAllByTestId("drop-action");
    fireEvent.dragOver(zones[0]!, { dataTransfer: transfer });
    fireEvent.drop(zones[0]!, { dataTransfer: transfer });
    expect(actionTypes()).toEqual(["assign_form", "create_activity", "update_enquiry"]);
    // The new step is selected and its side form is open.
    expect(screen.getByRole("dialog")).toHaveTextContent("Step 1: Send a form to fill");
  });

  it("drags a card to reorder", () => {
    render(<Harness />);
    const transfer = dataTransfer();
    const firstCard = screen.getByRole("button", { name: /1\. Create an activity/ }).closest("[draggable]")!;
    fireEvent.dragStart(firstCard, { dataTransfer: transfer });
    const zones = screen.getAllByTestId("drop-action");
    // Zones: above 1, above 2, after 2 — drop after the last step.
    fireEvent.drop(zones[2]!, { dataTransfer: transfer });
    expect(actionTypes()).toEqual(["update_enquiry", "create_activity"]);
  });

  it("refuses a condition dropped among the actions", () => {
    render(<Harness />);
    const transfer = dataTransfer();
    fireEvent.dragStart(screen.getByRole("button", { name: /^Condition/ }), { dataTransfer: transfer });
    const zone = screen.getAllByTestId("drop-action")[0]!;
    const accepted = fireEvent.dragOver(zone, { dataTransfer: transfer });
    // Not prevented: the browser will not allow the drop there.
    expect(accepted).toBe(true);
    fireEvent.drop(zone, { dataTransfer: transfer });
    expect(actionTypes()).toEqual(["create_activity", "update_enquiry"]);
  });

  it("moves and removes steps from the keyboard", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Move step 2 up" }));
    expect(actionTypes()).toEqual(["update_enquiry", "create_activity"]);
    fireEvent.click(screen.getByRole("button", { name: "Remove step 1" }));
    expect(actionTypes()).toEqual(["create_activity"]);
  });

  it("clicking a palette block adds it at the end and opens its form", () => {
    render(<Harness initialActions={[]} />);
    expect(screen.getByText(/Nothing happens yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Condition/ }));
    expect(JSON.parse(screen.getByTestId("conditions").textContent ?? "[]")).toHaveLength(1);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Condition 1")).toBeInTheDocument();
    expect(within(dialog).getByRole("combobox", { name: "When" })).toBeInTheDocument();
  });

  it("opens the trigger's side form from the WHEN card", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: /When · Enquiry\s*Created/ }));
    expect(within(screen.getByRole("dialog")).getByText("Trigger form")).toBeInTheDocument();
  });
});
