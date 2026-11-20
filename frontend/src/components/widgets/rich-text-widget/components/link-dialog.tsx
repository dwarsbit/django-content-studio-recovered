import { useQuery } from "@tanstack/react-query";
import type { Editor } from "@tiptap/core";
import * as R from "ramda";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PiCheckBold, PiMagnifyingGlassBold } from "react-icons/pi";
import { useDebounce } from "react-use";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { http } from "@/hooks/use-http";
import { cn } from "@/lib/utils";
import type { Model, SearchResultGroup } from "@/types";

// The search's minimum term length (the server's MIN_TERM_LENGTH).
const MIN_TERM_LENGTH = 2;

interface Target {
  model: string;
  id: string;
  url: string;
  title: string;
}

/**
 * Adds or edits the link at the selection: to an object in the studio
 * (Content), found through the global search of the linkable models, or
 * to a typed web address.
 */
export function LinkDialog({
  editor,
  linkModels,
  onClose,
}: {
  editor: Editor;
  // The models links can point to; empty: web addresses only.
  linkModels: Model[];
  onClose: VoidFunction;
}) {
  const { t } = useTranslation();
  const attrs = editor.getAttributes("link");
  const isEdit = editor.isActive("link");
  const current = linkModels.find((model) => model.label === attrs.linkModel);
  const canLinkContent = linkModels.length > 0;
  const [tab, setTab] = useState<"content" | "url">(
    canLinkContent && (!isEdit || attrs.linkModel) ? "content" : "url",
  );
  const [url, setUrl] = useState<string>(
    isEdit && !attrs.linkModel ? (attrs.href ?? "") : "",
  );
  const [target, setTarget] = useState<Target | null>(
    current && attrs.linkId
      ? {
          model: current.label,
          id: String(attrs.linkId),
          url: attrs.href ?? "",
          title: attrs.href ?? "",
        }
      : null,
  );
  // Unset: follows the tab (web addresses open in a new tab).
  const [newTab, setNewTab] = useState<boolean | null>(
    isEdit ? attrs.target === "_blank" : null,
  );
  const opensInNewTab = newTab ?? tab === "url";
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");

  useDebounce(() => setDebounced(term.trim()), 250, [term]);

  const { data: groups = [], isFetching } = useQuery({
    enabled: canLinkContent && debounced.length >= MIN_TERM_LENGTH,
    queryKey: ["link-search", debounced, linkModels.map((m) => m.label)],
    async queryFn() {
      const { data } = await http.get<SearchResultGroup[]>("/search", {
        params: {
          search: debounced,
          linkable: 1,
          models: linkModels.map((m) => m.label).join(","),
        },
      });

      return data;
    },
  });

  const href = tab === "content" ? target?.url : url.trim();
  const title = isEdit
    ? t("widgets.rich_text_widget.update_link")
    : t("widgets.rich_text_widget.set_link");

  function apply() {
    if (!href) {
      return;
    }

    let chain = editor.chain().focus();

    if (editor.isActive("link")) {
      chain = chain.extendMarkRange("link");
    } else if (editor.state.selection.empty) {
      // Without a selection, the link's text is the object's title or
      // the address.
      const text = tab === "content" && target ? target.title : href;
      const { from } = editor.state.selection;

      chain = chain
        .insertContent(text)
        .setTextSelection({ from, to: from + text.length });
    }

    chain
      .setLink({
        href,
        target: opensInNewTab ? "_blank" : null,
        linkModel: tab === "content" ? target?.model : null,
        linkId: tab === "content" ? target?.id : null,
      } as Parameters<ReturnType<Editor["chain"]>["setLink"]>[0])
      .run();
    // Typing goes on after the link, not over it.
    editor.commands.setTextSelection(editor.state.selection.to);
    onClose();
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="sm:max-w-[560px]"
        // Back to the text, not to the toolbar button.
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          editor.commands.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="sr-only">{title}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            apply();
          }}
        >
          <Tabs
            value={tab}
            onValueChange={(value) => setTab(value as "content" | "url")}
            className="gap-4"
          >
            {canLinkContent && (
              <TabsList>
                <TabsTrigger value="content">
                  {t("widgets.rich_text_widget.link_content")}
                </TabsTrigger>
                <TabsTrigger value="url">
                  {t("widgets.rich_text_widget.link_url")}
                </TabsTrigger>
              </TabsList>
            )}
            {canLinkContent && (
              <TabsContent value="content" className="flex flex-col gap-3">
                <InputGroup>
                  <InputGroupAddon>
                    <PiMagnifyingGlassBold className="text-muted-foreground" />
                  </InputGroupAddon>
                  <InputGroupInput
                    autoFocus
                    aria-label={t("widgets.rich_text_widget.link_search")}
                    placeholder={t("widgets.rich_text_widget.link_search")}
                    value={term}
                    onChange={(e) => setTerm(e.target.value)}
                  />
                </InputGroup>
                <div
                  role="listbox"
                  aria-label={t("widgets.rich_text_widget.link_results")}
                  className="h-[248px] overflow-y-auto scrollbar rounded-md border"
                >
                  {R.isEmpty(groups) && (
                    <p className="p-6 text-center text-sm text-muted-foreground">
                      {debounced.length >= MIN_TERM_LENGTH && !isFetching
                        ? t("widgets.rich_text_widget.link_no_results")
                        : t("widgets.rich_text_widget.link_search_hint")}
                    </p>
                  )}
                  {groups.map((group) => (
                    <div key={group.model} role="group" className="py-1">
                      <div className="px-3 pt-2 pb-1 text-xs font-medium text-muted-foreground first-letter:uppercase">
                        {group.verbose_name}
                      </div>
                      {group.results.map((item) => {
                        const selected =
                          target?.model === group.model &&
                          target.id === String(item.id);

                        return (
                          <button
                            type="button"
                            role="option"
                            aria-selected={selected}
                            key={item.id}
                            onClick={() =>
                              setTarget({
                                model: group.model,
                                id: String(item.id),
                                url: item.url ?? "",
                                title: item.title,
                              })
                            }
                            className={cn(
                              "flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent",
                              selected && "bg-accent text-accent-foreground",
                            )}
                          >
                            {group.icon && (
                              <span
                                className={cn(
                                  group.icon,
                                  "text-muted-foreground",
                                )}
                              />
                            )}
                            <span className="truncate">{item.title}</span>
                            <span className="ml-auto truncate max-w-[40%] text-xs text-muted-foreground">
                              {item.url}
                            </span>
                            {selected && (
                              <PiCheckBold className="size-4 shrink-0" />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
                {target && (
                  <p className="text-sm text-muted-foreground truncate">
                    {t("widgets.rich_text_widget.link_target", {
                      model:
                        linkModels.find((m) => m.label === target.model)
                          ?.verbose_name ?? target.model,
                      title: target.title,
                    })}
                  </p>
                )}
              </TabsContent>
            )}
            <TabsContent value="url">
              <Input
                autoFocus={!canLinkContent || tab === "url"}
                aria-label={t("widgets.rich_text_widget.link_url")}
                placeholder="https://"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </TabsContent>
          </Tabs>
          <Label className="flex items-center gap-2 font-normal">
            <Checkbox
              checked={opensInNewTab}
              onCheckedChange={(value) => setNewTab(value === true)}
            />
            {t("widgets.rich_text_widget.open_in_new_tab")}
          </Label>
          <DialogFooter>
            {isEdit && (
              <Button
                type="button"
                variant="destructive"
                className="mr-auto"
                onClick={() => {
                  editor
                    .chain()
                    .focus()
                    .extendMarkRange("link")
                    .unsetLink()
                    .run();
                  onClose();
                }}
              >
                {t("widgets.rich_text_widget.remove_link")}
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!href}>
              {title}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
