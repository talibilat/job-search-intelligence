import {
  cloneElement,
  isValidElement,
  useId,
  useState,
  type AriaAttributes,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type Key,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";

import "./primitives.css";

type ClassValue = string | false | null | undefined;

function cx(...values: ClassValue[]) {
  return values.filter(Boolean).join(" ");
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
}

/** Shared app button with a safe default `type` and visual variants. */
export function Button({
  className,
  type = "button",
  variant = "primary",
  ...props
}: ButtonProps) {
  return (
    <button
      className={cx("ui-button", `ui-button--${variant}`, className)}
      type={type}
      {...props}
    />
  );
}

interface InfoDisclosureProps {
  ariaLabel: string;
  buttonClassName: string;
  children: ReactNode;
  className: string;
  panelClassName: string;
  useButtonPrimitive?: boolean;
}

export function InfoDisclosure({
  ariaLabel,
  buttonClassName,
  children,
  className,
  panelClassName,
  useButtonPrimitive = false,
}: InfoDisclosureProps) {
  const infoId = useId();
  const [isPinned, setIsPinned] = useState(false);
  const [isPreviewed, setIsPreviewed] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);
  const isOpen = isPinned || (isPreviewed && !isDismissed);
  const controlProps = {
    "aria-controls": infoId,
    "aria-expanded": isOpen,
    "aria-label": ariaLabel,
    className: buttonClassName,
    onBlur: () => {
      setIsPreviewed(false);
      setIsDismissed(false);
    },
    onClick: () => {
      if (isPinned) {
        setIsPinned(false);
        setIsPreviewed(false);
        setIsDismissed(true);
        return;
      }

      setIsPinned(true);
      setIsDismissed(false);
    },
    onFocus: () => {
      setIsPreviewed(true);
      setIsDismissed(false);
    },
    onMouseEnter: () => {
      setIsPreviewed(true);
      setIsDismissed(false);
    },
    onMouseLeave: () => {
      setIsPreviewed(false);
      setIsDismissed(false);
    },
  };

  return (
    <div className={className}>
      {useButtonPrimitive ? (
        <Button {...controlProps} variant="ghost">
          i
        </Button>
      ) : (
        <button {...controlProps} type="button">
          i
        </button>
      )}
      {isOpen ? (
        <div className={panelClassName} id={infoId}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

/** Text input that maps the `invalid` state onto `aria-invalid`. */
export function TextInput({
  "aria-invalid": ariaInvalid,
  className,
  invalid = false,
  ...props
}: TextInputProps) {
  return (
    <input
      aria-invalid={invalid ? true : ariaInvalid}
      className={cx("ui-input", className)}
      {...props}
    />
  );
}

interface DescribedControlProps {
  "aria-describedby"?: string;
  "aria-invalid"?: AriaAttributes["aria-invalid"];
  id?: string;
}

interface FormFieldProps {
  children: ReactElement<DescribedControlProps>;
  error?: ReactNode;
  hint?: ReactNode;
  htmlFor: string;
  label: ReactNode;
}

function mergeIds(...ids: (string | undefined)[]) {
  const merged = Array.from(
    new Set(ids.flatMap((id) => id?.split(" ").filter(Boolean) ?? [])),
  ).join(" ");

  return merged.length > 0 ? merged : undefined;
}

/** Labelled control wrapper that wires hint and error text through `aria-describedby`. */
export function FormField({
  children,
  error,
  hint,
  htmlFor,
  label,
}: FormFieldProps) {
  const hintId = hint ? `${htmlFor}-hint` : undefined;
  const errorId = error ? `${htmlFor}-error` : undefined;
  const describedBy = mergeIds(hintId, errorId);
  const control = isValidElement<DescribedControlProps>(children)
    ? cloneElement(children, {
        "aria-describedby": mergeIds(
          children.props["aria-describedby"],
          describedBy,
        ),
        "aria-invalid": error ? true : children.props["aria-invalid"],
        id: htmlFor,
      })
    : children;

  return (
    <div className="ui-field">
      <label className="ui-label" htmlFor={htmlFor}>
        {label}
      </label>
      {control}
      {hint ? (
        <p className="ui-field-note" id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="ui-field-error" id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface AlertProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  "title"
> {
  title?: ReactNode;
  tone?: "danger" | "info" | "success" | "warning";
}

/** Static alert box; danger defaults to `role="alert"`, while callers opt into `status`. */
export function Alert({
  children,
  className,
  role,
  title,
  tone = "info",
  ...props
}: AlertProps) {
  const computedRole = role ?? (tone === "danger" ? "alert" : undefined);

  return (
    <div
      className={cx("ui-alert", `ui-alert--${tone}`, className)}
      role={computedRole}
      {...props}
    >
      {title ? <p className="ui-alert-title">{title}</p> : null}
      <div className="ui-alert-content">{children}</div>
    </div>
  );
}

export interface TabItem {
  content: ReactNode;
  disabled?: boolean;
  id: string;
  label: ReactNode;
}

export interface TabsProps {
  activeItemId?: string;
  className?: string;
  defaultItemId?: string;
  items: readonly TabItem[];
  label: string;
  onItemChange?: (itemId: string) => void;
}

/** Keyboard-operable tab set with roving focus across enabled tabs. */
export function Tabs({
  activeItemId,
  className,
  defaultItemId,
  items,
  label,
  onItemChange,
}: TabsProps) {
  const baseId = useId();
  const firstEnabledItem = items.find((item) => !item.disabled) ?? items[0];
  const [uncontrolledActiveId, setUncontrolledActiveId] = useState(
    defaultItemId ?? firstEnabledItem?.id,
  );
  const activeId = activeItemId ?? uncontrolledActiveId;
  const enabledItems = items.filter((item) => !item.disabled);
  const activeItem =
    items.find((item) => item.id === activeId && !item.disabled) ??
    firstEnabledItem;

  function getTabId(item: TabItem) {
    return `${baseId}-${item.id}-tab`;
  }

  function getPanelId(item: TabItem) {
    return `${baseId}-${item.id}-panel`;
  }

  function activateItem(item: TabItem | undefined) {
    if (!item || item.disabled) {
      return;
    }

    setUncontrolledActiveId(item.id);
    onItemChange?.(item.id);
    requestAnimationFrame(() =>
      document.getElementById(getTabId(item))?.focus(),
    );
  }

  function activateByOffset(offset: number) {
    if (!activeItem || enabledItems.length === 0) {
      return;
    }

    const activeIndex = enabledItems.findIndex(
      (item) => item.id === activeItem.id,
    );
    const nextIndex =
      (activeIndex + offset + enabledItems.length) % enabledItems.length;
    activateItem(enabledItems[nextIndex]);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      activateByOffset(1);
    }

    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      activateByOffset(-1);
    }

    if (event.key === "Home") {
      event.preventDefault();
      activateItem(enabledItems[0]);
    }

    if (event.key === "End") {
      event.preventDefault();
      activateItem(enabledItems.at(-1));
    }
  }

  if (items.length === 0 || !activeItem) {
    return null;
  }

  return (
    <div className={cx("ui-tabs", className)}>
      <div aria-label={label} className="ui-tab-list" role="tablist">
        {items.map((item) => {
          const selected = item.id === activeItem.id;

          return (
            <button
              aria-controls={getPanelId(item)}
              aria-disabled={item.disabled ? true : undefined}
              aria-selected={selected}
              className="ui-tab"
              disabled={item.disabled}
              id={getTabId(item)}
              key={item.id}
              onClick={() => activateItem(item)}
              onKeyDown={handleKeyDown}
              role="tab"
              tabIndex={selected ? 0 : -1}
              type="button"
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) => {
        const selected = item.id === activeItem.id;

        return (
          <div
            aria-labelledby={getTabId(item)}
            className="ui-tab-panel"
            hidden={!selected}
            id={getPanelId(item)}
            key={item.id}
            role="tabpanel"
          >
            {item.content}
          </div>
        );
      })}
    </div>
  );
}

type DataTableCellValue = string | number | null | undefined;

interface DataTableColumnBase {
  align?: "left" | "right";
  header: ReactNode;
}

export type DataTableColumn<TRow extends object> = DataTableColumnBase &
  {
    [TKey in keyof TRow & string]: TRow[TKey] extends DataTableCellValue
      ? {
          key: TKey;
          render?: (row: TRow) => ReactNode;
        }
      : {
          key: TKey;
          render: (row: TRow) => ReactNode;
        };
  }[keyof TRow & string];

type ResolvedDataTableColumn<TRow extends object> = DataTableColumnBase & {
  key: keyof TRow & string;
  render?: (row: TRow) => ReactNode;
};

export interface DataTableProps<TRow extends object> {
  caption: ReactNode;
  columns: readonly DataTableColumn<TRow>[];
  emptyMessage?: ReactNode;
  rowKey: (row: TRow) => Key;
  rows: readonly TRow[];
}

function renderCellValue<TRow extends object>(
  row: TRow,
  column: ResolvedDataTableColumn<TRow>,
) {
  if (column.render) {
    return column.render(row);
  }

  const value = row[column.key];

  if (typeof value === "string" || typeof value === "number") {
    return value;
  }

  if (value == null) {
    return "";
  }

  throw new Error(
    "DataTable columns for non-scalar values must define render.",
  );
}

/** Captioned data table; non-scalar columns must provide `render`. */
export function DataTable<TRow extends object>({
  caption,
  columns,
  emptyMessage = "No rows to display.",
  rowKey,
  rows,
}: DataTableProps<TRow>) {
  return (
    <div className="ui-table-wrap">
      <table className="ui-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                className={cx(column.align === "right" && "ui-cell--right")}
                key={column.key}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length > 0 ? (
            rows.map((row) => (
              <tr key={rowKey(row)}>
                {columns.map((column) => (
                  <td
                    className={cx(column.align === "right" && "ui-cell--right")}
                    key={column.key}
                  >
                    {renderCellValue(row, column)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td className="ui-empty-cell" colSpan={columns.length}>
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
