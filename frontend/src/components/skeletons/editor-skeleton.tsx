import * as R from "ramda";
import { useTranslation } from "react-i18next";
import { PiArrowLeftBold } from "react-icons/pi";

import { getMainColumnWidth } from "@/components/content-editor/edit-width";
import { Button } from "@/components/ui/button";
import { DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminInfo } from "@/hooks/use-admin-info";
import { useDiscover } from "@/hooks/use-discover";
import { cn } from "@/lib/utils";
import {
  type EditWidth,
  FieldWidget,
  type FormField,
  type FormLayout,
  type FormSet,
  type Model,
} from "@/types";

// The height of a field's placeholder follows its widget: a line for an
// input, a box for a text area, an editor, or a picture.
const BOX: string[] = [
  FieldWidget.TextAreaWidget,
  FieldWidget.MarkdownWidget,
  FieldWidget.CodeWidget,
  FieldWidget.JSONWidget,
  FieldWidget.KeyValueWidget,
  FieldWidget.ListWidget,
  FieldWidget.FileWidget,
];
const EDITOR: string[] = [
  FieldWidget.RichTextWidget,
  FieldWidget.BlockWidget,
  FieldWidget.MapWidget,
];
const PICTURE: string[] = [
  FieldWidget.MediaWidget,
  FieldWidget.CoverImageWidget,
  FieldWidget.ManyMediaWidget,
];
const INLINE: string[] = [FieldWidget.CheckboxWidget, FieldWidget.SwitchWidget];

/**
 * The editor while its object loads. The layout comes from the studio,
 * so the skeleton has the real tabs, card titles and field labels; only
 * the values are placeholders. Form sets and fields with a condition are
 * left out: whether they show depends on the values.
 */
export function EditorSkeleton({
  model,
  id,
  dialog = false,
  inline = false,
  width,
}: {
  model: Model;
  id?: string | null;
  dialog?: boolean;
  // An inline row: published with its parent, no comments.
  inline?: boolean;
  width?: EditWidth;
}) {
  const { t } = useTranslation();
  const { data: discover } = useDiscover();
  const { main, sidebar, inlines } = model.admin.edit;
  const isSingleton = model.admin.is_singleton;
  const groups = main.filter((group) => !R.isEmpty(group.label) && !group.when);
  const showTabs =
    main.length > 1 || groups.length > 0 || (!R.isEmpty(inlines) && !!id);
  const tabs = [
    ...(groups.length > 0
      ? groups.map((group) => group.label)
      : [t("common.general")]),
    ...(id
      ? inlines.map(
          (inline) =>
            discover?.models.find(R.whereEq({ label: inline.model }))
              ?.verbose_name_plural ?? "",
        )
      : []),
  ];
  const formSets = (main.find((group) => !group.when)?.formsets ?? []).filter(
    (formSet) => !formSet.when,
  );
  const sidebarSets = (sidebar ?? []).filter((formSet) => !formSet.when);
  const publishing = !inline && !!model.admin.list.publishing;
  const comments =
    !dialog && !inline && !isSingleton && !!id && !!model.admin.comments;
  const hasSidebar = sidebarSets.length > 0 || publishing || comments;

  const plural = (
    <span
      className={cn(
        "shrink-0 first-letter:uppercase",
        id && "text-muted-foreground font-medium max-lg:hidden",
      )}
    >
      {model.verbose_name_plural}
    </span>
  );

  return (
    <div
      aria-busy
      data-testid="editor-skeleton"
      className="flex-1 flex flex-col overflow-hidden w-full"
    >
      <DialogOrFragment dialog={dialog}>
        <PageHeader
          heading={dialog ? "div" : "h1"}
          back={
            !isSingleton && (
              <Button
                size="icon-sm"
                variant="ghost"
                className="-ml-2 text-muted-foreground"
                disabled
                aria-label={t("editor.back_to_list")}
              >
                <PiArrowLeftBold />
              </Button>
            )
          }
          icon={model.admin.icon && <span className={model.admin.icon} />}
          title={
            <span className="flex items-center gap-1.5 min-w-0">
              {dialog ? (
                <DialogTitle className="text-base leading-normal font-medium shrink-0 first-letter:uppercase text-muted-foreground">
                  {model.verbose_name_plural}
                </DialogTitle>
              ) : (
                plural
              )}
              {id && (
                <>
                  <span
                    aria-hidden
                    className="text-muted-foreground/50 max-lg:hidden"
                  >
                    /
                  </span>
                  <Skeleton className="h-4 w-56 max-w-full" />
                </>
              )}
            </span>
          }
          actions={
            <>
              <Skeleton className="size-8 rounded-lg" />
              <Button disabled>{t("common.save")}</Button>
            </>
          }
        />
      </DialogOrFragment>
      <div className="@container flex flex-col items-center overflow-hidden">
        <div className="flex flex-col @3xl:flex-row p-6 w-full max-w-[1280px] gap-6 justify-center">
          <div
            className={cn(
              "w-full @3xl:flex-1 min-w-0",
              getMainColumnWidth(width ?? model.admin.edit.width),
            )}
          >
            {showTabs && (
              <div className="mb-5 flex gap-6 border-b overflow-hidden">
                {tabs.map((label, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      "pb-2.5 -mb-px text-sm font-medium whitespace-nowrap first-letter:uppercase",
                      idx === 0
                        ? "border-b-2 border-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {label}
                  </div>
                ))}
              </div>
            )}
            <div className="space-y-5">
              {formSets.map((formSet, idx) => (
                <FormSetSkeleton key={idx} formSet={formSet} model={model} />
              ))}
            </div>
          </div>
          {hasSidebar && (
            <div className="shrink-0 w-full @3xl:w-[320px] space-y-4">
              {publishing && (
                <section className="rounded-lg border bg-card shadow-xs">
                  <div className="px-5 py-3 border-b flex items-center justify-between">
                    <h4 className="font-semibold">{t("publishing.title")}</h4>
                    <Skeleton className="h-5 w-16 rounded-full" />
                  </div>
                  <div className="p-5 space-y-3">
                    <Skeleton className="h-3.5 w-full" />
                    <Skeleton className="h-3.5 w-3/4" />
                    <Skeleton className="h-8 w-full rounded-lg" />
                  </div>
                </section>
              )}
              {comments && (
                <section className="rounded-lg border bg-card shadow-xs">
                  <div className="px-5 py-3 border-b">
                    <h4 className="font-semibold">{t("comments.title")}</h4>
                  </div>
                  <div className="p-5 space-y-3">
                    <Skeleton className="h-3 w-32" />
                    <Skeleton className="h-16 w-full rounded-lg" />
                  </div>
                </section>
              )}
              {sidebarSets.map((formSet, idx) => (
                <FormSetSkeleton key={idx} formSet={formSet} model={model} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// The header sits in a DialogHeader inside a dialog, like the editor's.
function DialogOrFragment({
  dialog,
  children,
}: {
  dialog: boolean;
  children: React.ReactNode;
}) {
  return dialog ? (
    <DialogHeader className="z-10 block">{children}</DialogHeader>
  ) : (
    children
  );
}

function FormSetSkeleton({
  formSet,
  model,
}: {
  formSet: FormSet;
  model: Model;
}) {
  return (
    <section className="rounded-lg border bg-card shadow-xs w-full">
      {(formSet.title || formSet.description) && (
        <div className="px-5 py-3 border-b">
          {formSet.title && (
            <h4 className="font-semibold first-letter:uppercase">
              {formSet.title}
            </h4>
          )}
          {formSet.description ? (
            <div className="text-xs text-muted-foreground">
              {formSet.description}
            </div>
          ) : null}
        </div>
      )}
      <div className="@container p-5 space-y-5">
        {formSet.fields.map((field, idx) => {
          if (R.has("fields", field)) {
            const fields = (field as FormLayout).fields.filter((f) => !f.when);

            return (
              fields.length > 0 && (
                <div
                  key={idx}
                  className="grid gap-4 grid-cols-1 @sm:[grid-template-columns:repeat(var(--columns),minmax(0,1fr))]"
                  style={{ "--columns": fields.length } as React.CSSProperties}
                >
                  {fields.map((inner) => (
                    <FieldSkeleton
                      key={inner.name}
                      field={inner}
                      model={model}
                    />
                  ))}
                </div>
              )
            );
          }

          return (
            !(field as FormField).when && (
              <FieldSkeleton
                key={idx}
                field={field as FormField}
                model={model}
              />
            )
          );
        })}
      </div>
    </section>
  );
}

function FieldSkeleton({ field, model }: { field: FormField; model: Model }) {
  const { data: info } = useAdminInfo();
  const modelField = model.fields[field.name];
  const label = field.label || modelField?.verbose_name;
  const widget =
    field.widget?.name ??
    modelField?.widget_class ??
    info?.widgets[modelField?.type ?? ""]?.name ??
    "";

  // Components (callouts, activity logs, a translation status) get a
  // block of their own.
  if (field.type === "component") {
    return <Skeleton className="h-16 w-full rounded-lg" />;
  }

  const labelNode = (
    <div className="text-sm font-medium leading-none first-letter:uppercase">
      {label}
    </div>
  );

  if (INLINE.includes(widget)) {
    return (
      <div className="flex items-center gap-2">
        <Skeleton
          className={
            widget === FieldWidget.SwitchWidget
              ? "h-[18px] w-8 rounded-full"
              : "size-4 rounded-[4px]"
          }
        />
        {labelNode}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {labelNode}
      <Skeleton
        className={cn(
          "w-full rounded-lg",
          EDITOR.includes(widget)
            ? "h-56"
            : BOX.includes(widget)
              ? "h-24"
              : PICTURE.includes(widget)
                ? "aspect-video"
                : "h-9",
        )}
      />
    </div>
  );
}
