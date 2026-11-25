# Skeleton

A soft block that pulses where content is still loading, in the shape of
that content.

- Use it for a page or card whose layout is known before its data: draw the
  real headings, labels and columns, and a Skeleton only where the values go.
- Match the size of what it stands for: `h-3.5` and a width for a line of
  text, `h-9 w-full rounded-lg` for an input, `aspect-[4/3]` for a picture.
  Vary the widths of text lines so they read as text.
- Show it only for a slow load: the admin waits 200 ms before it appears and
  then keeps it at least 300 ms, so a quick load goes straight to the content.
- Use `Spinner` instead for a running action, like a button that saves.

The pulse stops when the system asks for reduced motion. The consumer
provides only the size and shape.
