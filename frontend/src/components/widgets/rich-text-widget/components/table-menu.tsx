import type { Editor } from "@tiptap/core";
import { useEditorState, useTiptap } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";
import {
  PiColumnsPlusLeftBold,
  PiColumnsPlusRightBold,
  PiRowsPlusBottomBold,
  PiRowsPlusTopBold,
  PiTableBold,
  PiTrashBold,
} from "react-icons/pi";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { Toggle } from "@/components/ui/toggle";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/** Inserts a 3 by 3 table with a header row at the cursor. */
export function TableButton() {
  const { t } = useTranslation();
  const { editor } = useTiptap();
  const label = t("widgets.rich_text_widget.insert_table");

  return (
    <Tooltip>
      <TooltipContent>{label}</TooltipContent>
      <TooltipTrigger asChild>
        <Button
          size="sm"
          variant="ghost"
          aria-label={label}
          onClick={() =>
            editor
              .chain()
              .focus()
              .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
              .run()
          }
        >
          <PiTableBold />
        </Button>
      </TooltipTrigger>
    </Tooltip>
  );
}

function Tip({ label, children }: { label: string; children: ReactElement }) {
  return (
    <Tooltip>
      <TooltipContent>{label}</TooltipContent>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
    </Tooltip>
  );
}

/** The DOM element of the table the selection is in. */
function tableElement(editor: Editor): HTMLElement | null {
  const { view, state } = editor;
  let node: Node | null = view.domAtPos(state.selection.from).node;

  while (node && node.nodeName !== "TABLE") {
    node = node.parentNode;
  }

  return node as HTMLElement | null;
}

/** Whether the first row of the table the selection is in is a header. */
function hasHeaderRow(editor: Editor): boolean {
  const { $from } = editor.state.selection;

  for (let depth = $from.depth; depth > 0; depth--) {
    const node = $from.node(depth);

    if (node.type.name === "table") {
      return node.firstChild?.firstChild?.type.name === "tableHeader";
    }
  }

  return false;
}

/**
 * The toolbar above the table the cursor is in: rows, columns, the
 * header row and deleting.
 */
export function TableMenu({ editor }: { editor: Editor }) {
  const { t } = useTranslation();
  const headerRow = useEditorState({
    editor,
    selector: ({ editor }) => editor.isActive("table") && hasHeaderRow(editor),
  });
  const run =
    (command: (chain: ReturnType<Editor["chain"]>) => unknown) => () =>
      command(editor.chain().focus());

  return (
    <BubbleMenu
      editor={editor}
      pluginKey="tableMenu"
      shouldShow={({ editor, view, element }) =>
        editor.isEditable &&
        editor.isActive("table") &&
        (view.hasFocus() || element.contains(document.activeElement))
      }
      options={{ placement: "top-start", offset: 8 }}
      getReferencedVirtualElement={() => {
        const element = tableElement(editor);

        return element
          ? { getBoundingClientRect: () => element.getBoundingClientRect() }
          : null;
      }}
    >
      <div
        className="rich-text-table-menu flex items-center gap-1 rounded-md border bg-popover text-popover-foreground p-1 shadow-md"
        aria-label={t("widgets.rich_text_widget.table")}
        role="toolbar"
      >
        <Tip label={t("widgets.rich_text_widget.add_row_before")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("widgets.rich_text_widget.add_row_before")}
            onClick={run((c) => c.addRowBefore().run())}
          >
            <PiRowsPlusTopBold />
          </Button>
        </Tip>
        <Tip label={t("widgets.rich_text_widget.add_row_after")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("widgets.rich_text_widget.add_row_after")}
            onClick={run((c) => c.addRowAfter().run())}
          >
            <PiRowsPlusBottomBold />
          </Button>
        </Tip>
        <Tip label={t("widgets.rich_text_widget.add_column_before")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("widgets.rich_text_widget.add_column_before")}
            onClick={run((c) => c.addColumnBefore().run())}
          >
            <PiColumnsPlusLeftBold />
          </Button>
        </Tip>
        <Tip label={t("widgets.rich_text_widget.add_column_after")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("widgets.rich_text_widget.add_column_after")}
            onClick={run((c) => c.addColumnAfter().run())}
          >
            <PiColumnsPlusRightBold />
          </Button>
        </Tip>
        <Separator orientation="vertical" className="h-6!" />
        <Toggle
          size="sm"
          pressed={headerRow}
          onPressedChange={run((c) => c.toggleHeaderRow().run())}
        >
          {t("widgets.rich_text_widget.header_row")}
        </Toggle>
        <Separator orientation="vertical" className="h-6!" />
        <DropdownMenu>
          <Tip label={t("common.delete")}>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost" aria-label={t("common.delete")}>
                <PiTrashBold />
              </Button>
            </DropdownMenuTrigger>
          </Tip>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={run((c) => c.deleteRow().run())}>
              {t("widgets.rich_text_widget.delete_row")}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={run((c) => c.deleteColumn().run())}>
              {t("widgets.rich_text_widget.delete_column")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onSelect={run((c) => c.deleteTable().run())}
            >
              {t("widgets.rich_text_widget.delete_table")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </BubbleMenu>
  );
}
