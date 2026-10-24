/**
 * The email composer: blocks in, HTML out, and the same blocks back when the
 * template is reopened.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  EmailComposer,
  blocksToHtml,
  htmlToBlocks,
  type EmailBlock,
} from "@/components/communication/email-composer";

describe("blocksToHtml / htmlToBlocks", () => {
  const blocks: EmailBlock[] = [
    { kind: "heading", text: "Welcome" },
    { kind: "text", text: "Hello {{ student.name }}.\n\nYour batch starts Monday." },
    { kind: "button", text: "Open the portal", href: "https://lms.example" },
  ];

  it("round-trips exactly, rather than guessing blocks back out of HTML", () => {
    expect(htmlToBlocks(blocksToHtml(blocks))).toEqual(blocks);
  });

  it("renders paragraphs from blank lines and escapes what the author typed", () => {
    const html = blocksToHtml([{ kind: "text", text: "a & b\n\n<script>x</script>" }]);
    expect(html).toContain("<p>a &amp; b</p>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });

  it("keeps a token as written, for the server to substitute", () => {
    expect(blocksToHtml(blocks)).toContain("{{ student.name }}");
  });

  it("emits only markup the server's email sanitiser keeps", () => {
    const html = blocksToHtml([
      { kind: 'heading', text: 'Welcome' },
      { kind: 'button', text: 'Open', href: 'https://grras.example' },
      { kind: 'spacer' },
      { kind: 'image', src: 'https://grras.example/logo.png', alt: 'GRRAS' },
    ]);

    // `style` is refused outright on the way out (it is how content hides),
    // so a styled button would reach the recipient unstyled. The colour
    // rides on `bgcolor` instead.
    expect(html).not.toContain('style=');
    expect(html).toContain('bgcolor="#FFF3EA"');
    expect(html).toContain('<h2>Welcome</h2>');
  });

  it("says nothing about a body it did not write", () => {
    expect(htmlToBlocks("<p>Written somewhere else</p>")).toBeNull();
    expect(htmlToBlocks("<!--grras-blocks:not json-->")).toBeNull();
  });

  it("survives a block containing the comment terminator", () => {
    // Unencoded, this would close the comment early and spill the rest of
    // the block list into the body as markup.
    const nasty: EmailBlock[] = [{ kind: "text", text: "a --> b" }];
    expect(htmlToBlocks(blocksToHtml(nasty))).toEqual(nasty);
  });
});

describe("EmailComposer", () => {
  it("adds a block, and hands back HTML carrying it", () => {
    const onChange = vi.fn();
    render(<EmailComposer html="" variables={[]} onChange={onChange} />);

    expect(screen.getByText(/No content here/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Heading" }));

    expect(onChange).toHaveBeenCalled();
    const html = onChange.mock.calls.at(-1)![0] as string;
    expect(htmlToBlocks(html)).toEqual([{ kind: "heading", text: "Your heading" }]);
  });

  it("moves a block and keeps the order in the HTML", () => {
    const onChange = vi.fn();
    const html = blocksToHtml([
      { kind: "heading", text: "First" },
      { kind: "text", text: "Second" },
    ]);
    render(<EmailComposer html={html} variables={[]} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Move block 2 up" }));
    const next = htmlToBlocks(onChange.mock.calls.at(-1)![0] as string);
    expect(next?.map((block) => block.kind)).toEqual(["text", "heading"]);
  });

  it("removes a block", () => {
    const onChange = vi.fn();
    render(
      <EmailComposer
        html={blocksToHtml([{ kind: "divider" }])}
        variables={[]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove block 1" }));
    expect(htmlToBlocks(onChange.mock.calls.at(-1)![0] as string)).toEqual([]);
  });

  it("inserts a token into the block being edited", () => {
    const onChange = vi.fn();
    render(
      <EmailComposer
        html={blocksToHtml([{ kind: "text", text: "Hi " }])}
        variables={["student.name"]}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "student.name" }));
    const blocks = htmlToBlocks(onChange.mock.calls.at(-1)![0] as string);
    expect(blocks?.[0]?.text).toBe("Hi {{ student.name }}");
  });

  it("offers no tokens to insert when the template allows none", () => {
    render(<EmailComposer html="" variables={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/Add the variables this template may use/)).toBeInTheDocument();
  });

  it("leaves a body written elsewhere as HTML rather than rearranging it", () => {
    render(
      <EmailComposer html="<p>Hand written</p>" variables={[]} onChange={vi.fn()} />,
    );
    expect(screen.getByText(/not written in the composer/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Body \(HTML\)/)).toHaveValue("<p>Hand written</p>");
  });

  it("previews at phone width as well as desktop", () => {
    render(
      <EmailComposer
        html={blocksToHtml([{ kind: "heading", text: "Welcome" }])}
        variables={[]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Desktop preview" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Phone preview" }));
    expect(screen.getByRole("button", { name: "Phone preview" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // The preview is the same sandboxed, script-less frame the server-rendered
    // one uses.
    expect(screen.getByTestId("template-html-preview")).toHaveAttribute("sandbox", "");
  });
});
