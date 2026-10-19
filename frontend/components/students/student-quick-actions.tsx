'use client';

/**
 * The things people do to a student, from the student's own page: record a
 * payment, plan a follow-up, put them on a batch, move them, re-send their
 * invitation. Before, each lived on a different screen and somebody looking
 * at the student had to know which one.
 *
 * Every entry follows the caller's own capabilities, so a trainer sees none
 * of them and a counsellor sees the desk's. The server checks again on every
 * request; this only decides what is offered.
 */

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

import { PlanFollowUp } from '@/components/admissions/plan-follow-up';
import { useAuth } from '@/components/auth-provider';
import { Confirm } from '@/components/confirm';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/toast';
import { errorMessage } from '@/lib/api';
import { Capability } from '@/lib/capabilities';
import { sendCredentialLink } from '@/lib/people';

export function StudentQuickActions({
  studentId,
  userId,
  email,
  invitationAccepted,
  onOpenTab,
  onChanged,
}: {
  studentId: string;
  userId: string;
  email: string;
  /** They set a password of their own; no invitation is needed. */
  invitationAccepted: boolean;
  /** Opens a tab on this page — the fees tab for "Record a payment". */
  onOpenTab: (tab: 'fees' | 'activities') => void;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const [confirmingInvite, setConfirmingInvite] = useState(false);
  const [sending, setSending] = useState(false);

  const mayPay = can(Capability.feeManageAny);
  const mayEnrol = can(Capability.enrolmentCreate);
  const mayTransfer = mayEnrol && can(Capability.enrolmentUpdateAny);
  const mayInvite = !invitationAccepted && can(Capability.userUpdateAny);
  const mayLog = can(Capability.activityCreate);
  const anyInMenu = mayPay || mayEnrol || mayTransfer || mayInvite || mayLog;

  async function invite() {
    setSending(true);
    try {
      const answer = await sendCredentialLink(userId, 'password_reset');
      if (answer.sent) {
        toast({ title: 'Invitation sent', description: `A new link to set a password went to ${email}.` });
      } else {
        toast({ title: 'Could not send the invitation', description: answer.detail, variant: 'error' });
      }
    } catch (cause) {
      toast({ title: 'Could not send the invitation', description: errorMessage(cause), variant: 'error' });
    } finally {
      setSending(false);
      setConfirmingInvite(false);
    }
  }

  return (
    <>
      {mayLog ? <PlanFollowUp studentId={studentId} onCreated={onChanged} /> : null}
      {anyInMenu ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" size="sm">
              Actions
              <ChevronDown className="size-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>For this student</DropdownMenuLabel>
            {mayPay ? (
              <DropdownMenuItem onSelect={() => onOpenTab('fees')}>Record a payment</DropdownMenuItem>
            ) : null}
            {mayLog ? (
              <DropdownMenuItem onSelect={() => onOpenTab('activities')}>
                Log an activity
              </DropdownMenuItem>
            ) : null}
            {mayEnrol ? (
              <DropdownMenuItem onSelect={() => router.push(`/admissions/${studentId}`)}>
                Enrol on a batch
              </DropdownMenuItem>
            ) : null}
            {mayTransfer ? (
              <DropdownMenuItem
                onSelect={() => router.push(`/admissions/transfer?student=${studentId}`)}
              >
                Move to another batch
              </DropdownMenuItem>
            ) : null}
            {mayInvite ? (
              <DropdownMenuItem onSelect={() => setConfirmingInvite(true)}>
                Resend invitation
              </DropdownMenuItem>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      <Confirm
        open={confirmingInvite}
        title="Resend their invitation?"
        description={`A new link to set a password goes to ${email}. The old link stops working.`}
        confirmLabel="Send invitation"
        confirmVariant="primary"
        isConfirming={sending}
        onConfirm={() => void invite()}
        onCancel={() => setConfirmingInvite(false)}
      />
    </>
  );
}
