Mask-AIT was created by a Nigerian that lives in Birmingham and he made this project with a series of test and reiteration, it's open source and available to those who have the commercial license

A lightweight Gradio-based image masking and region-merging service.

The project allows you to:

- Upload an image.
- Paint the exact region that needs editing.
- Generate a standard grayscale mask.
- Generate a white/blur obfuscation representation.
- Generate a soft obfuscation representation.
- Download the appropriate image/mask for use with an external image-editing model.
- Upload the externally edited result.
- Merge only the selected region back into the untouched original.

The project does **not** run an image-generation model.

No GPU is required.

No ComfyUI is required.

No model weights are required.

---

## Architecture

The service is deliberately small:

```text
                    ┌─────────────────────┐
                    │      Original       │
                    │       Image         │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Gradio Editor    │
                    │                     │
                    │   Paint Region      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Mask Generator   │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
        Standard Mask    Obfuscated Image   Soft Obfuscation
              │                │                │
              └────────────────┼────────────────┘
                               │
                               ▼
                     External Image Model
                               │
                               ▼
                       Edited Image
                               │
                               ▼
                    Upload Back to Service
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Masked Merge      │
                    └──────────┬──────────┘
                               │
                               ▼
                        Final Image
