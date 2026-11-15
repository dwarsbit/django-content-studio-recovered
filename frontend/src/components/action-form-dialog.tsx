import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { PiWarningCircleBold } from "react-icons/pi";
import { toast } from "sonner";

import { Conditional } from "@/components/content-editor/conditional";
import { FormField } from "@/components/content-editor/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Form } from "@/components/ui/form";
import {
  type ActionValues,
  getDialogModel,
  getInitialValues,
} from "@/lib/action-form";
import { applyFieldErrors, getNonFieldErrors } from "@/lib/server-errors";
import { getErrorMessage } from "@/lib/utils";
import type { FormField as IFormField, Model } from "@/types";

/**
 * The dialog of an action with inputs: the action's fields, rendered
 * with the edit form's widgets and conditions, and a submit button
 * named after the action. Errors the server reports land under their
 * fields; the dialog closes once the action has run.
 */
export function ActionFormDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  destructive,
  model,
  fields,
  initialValues,
  onSubmit,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  title: string;
  description?: React.ReactNode;
  submitLabel: string;
  destructive?: boolean;
  model: Model;
  fields: IFormField[];
  initialValues?: ActionValues;
  // Runs the action; a rejection with field errors keeps the dialog
  // open and shows them.
  onSubmit(values: ActionValues): Promise<unknown>;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {open && (
          <ActionForm
            title={title}
            description={description}
            submitLabel={submitLabel}
            destructive={destructive}
            model={model}
            fields={fields}
            initialValues={initialValues}
            onCancel={() => onOpenChange(false)}
            onSubmit={async (values) => {
              await onSubmit(values);
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ActionForm({
  title,
  description,
  submitLabel,
  destructive,
  model,
  fields,
  initialValues,
  onCancel,
  onSubmit,
}: {
  title: string;
  description?: React.ReactNode;
  submitLabel: string;
  destructive?: boolean;
  model: Model;
  fields: IFormField[];
  initialValues?: ActionValues;
  onCancel(): void;
  onSubmit(values: ActionValues): Promise<unknown>;
}) {
  const { t } = useTranslation();
  const dialogModel = useMemo(
    () => getDialogModel(model, fields),
    [model, fields],
  );
  const form = useForm<ActionValues>({
    // Started once, when the dialog opens.
    defaultValues: getInitialValues(dialogModel, fields, initialValues),
  });
  const [nonFieldErrors, setNonFieldErrors] = useState<string[]>([]);

  async function submit(values: ActionValues) {
    setNonFieldErrors([]);

    try {
      await onSubmit(values);
    } catch (e) {
      if (applyFieldErrors(e, form.setError as never)) {
        setNonFieldErrors(getNonFieldErrors(e));
      } else {
        toast.error(getErrorMessage(e));
      }
    }
  }

  return (
    <Form {...form}>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {description && <DialogDescription>{description}</DialogDescription>}
      </DialogHeader>
      <form
        id="action-form"
        className="grid gap-4 min-w-0"
        onSubmit={form.handleSubmit(submit)}
      >
        {nonFieldErrors.length > 0 && (
          <Alert variant="destructive">
            <PiWarningCircleBold />
            <AlertDescription>
              {nonFieldErrors.map((message) => (
                <p key={message}>{message}</p>
              ))}
            </AlertDescription>
          </Alert>
        )}
        {fields.map((field) => (
          <Conditional key={field.name} when={field.when} fields={[field.name]}>
            <FormField formField={field} model={dialogModel} />
          </Conditional>
        ))}
      </form>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          type="submit"
          form="action-form"
          variant={destructive ? "destructive" : "default"}
          isLoading={form.formState.isSubmitting}
        >
          {submitLabel}
        </Button>
      </DialogFooter>
    </Form>
  );
}
