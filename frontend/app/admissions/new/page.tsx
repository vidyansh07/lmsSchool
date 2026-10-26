import { redirect } from 'next/navigation';

/**
 * The fast one-screen registration wizard used to live here.
 *
 * There were two ways to register a student. This one did person → course →
 * batch → enrol in a single atomic confirm; the desk's own flow did person →
 * guardians → charges → payment, and had a fifth step named "Batch Details"
 * with no page behind it. So each was missing something the other had, and
 * every counsellor had to know which door to use for which job.
 *
 * The desk flow is the one that survives, because it is the only one that
 * takes guardians and money. It has since gained everything this screen did:
 * the batch step, the duplicate check with its override reason, the referral,
 * the fee decided (or deliberately not decided) at the desk, and registering
 * a lead opened with `?enquiry=<id>`.
 *
 * A redirect rather than a deletion. This URL is in bookmarks, in links
 * across the product, and in whatever notes a counsellor keeps; breaking
 * those to be tidy would be paid for by the people using it. The query string
 * is carried through, so "Register this lead" still lands on a pre-filled
 * form.
 */
export default async function RegisterStudentRedirect({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const enquiry = params.enquiry;
  const id = Array.isArray(enquiry) ? enquiry[0] : enquiry;
  redirect(id ? `/students/new?enquiry=${encodeURIComponent(id)}` : '/students/new');
}
