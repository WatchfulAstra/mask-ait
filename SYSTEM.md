# SYSTEM.md
# Universal Image Mask Service

## 1. Purpose

This project is a lightweight image-masking and region-merging service.

It does NOT run an image-generation model.

It does NOT require a GPU.

It does NOT depend on ComfyUI.

It does NOT require model weights.

Its purpose is to prepare an image for editing by an external
image-generation/editing system and then safely merge the external
result back into the original image.

The server is responsible for:

1. Receiving an image.
2. Allowing the user to paint an editable region.
3. Creating a canonical grayscale mask.
4. Creating an obfuscated image representation.
5. Creating a softened obfuscated representation.
6. Keeping the original image untouched.
7. Accepting an externally generated result.
8. Merging only the selected region back into the original.
9. Returning the final image.

The external image model is responsible only for generating the
replacement content.


---

# 2. Core Design Principle

The original image is the source of truth.

Once the user creates a mask, the original image must be preserved
in application state.

The original must NOT be overwritten by:

- the mask,
- the obfuscated image,
- an externally generated image,
- a preview,
- a failed generation,
- or an intermediate operation.

The original image is only replaced conceptually when the user
explicitly performs the final merge.


---

# 3. Basic Workflow

The intended workflow is:

    Upload Image
         |
         v
    Paint Region
         |
         v
    Generate Masks
         |
         +--------------------+
         |                    |
         v                    v
    Standard Mask       Obfuscated Image
         |                    |
         |                    |
         +----------+---------+
                    |
                    v
          External Image Model
                    |
                    v
          Edited Image Returned
                    |
                    v
             Upload Result
                    |
                    v
                 Merge
                    |
                    v
             Final Image


The external model does not need to run on this server.


---

# 4. Mask Concept

The user paints the area that should be edited.

Example:

    Original image:
    
    [ PERSON + CLOTHING + BACKGROUND ]

    User paints:
    
    [ FACE ]

The resulting canonical mask represents:

    WHITE / HIGH VALUE = EDITABLE
    BLACK / LOW VALUE  = PROTECTED

The exact grayscale values may contain intermediate values around
the edges because of antialiasing and feathering.


---

# 5. Canonical Mask

The canonical mask is the most important representation.

It is a grayscale PNG.

Properties:

- Same width as the original image.
- Same height as the original image.
- Mode: `L`.
- White represents the editable region.
- Black represents the protected region.
- Intermediate grayscale values are allowed.
- PNG is preferred because it is lossless.

The canonical mask is the authoritative mask used for merging.

The obfuscated representations must NEVER replace the canonical mask.


---

# 6. Obfuscation Representation

Some external image-editing systems may respond better when the
unselected portions of an image contain very little useful visual
information.

For that reason the service generates an obfuscated representation.

Conceptually:

    EDITABLE REGION
        |
        | remains clear
        v

    [ FACE ]

    PROTECTED REGION
        |
        | washed / blurred toward white
        v

    [ WHITE / LOW-INFORMATION AREA ]


The purpose is to reduce the amount of information available to an
external image model outside the intended editing region.

This representation is NOT the source of truth for merging.


---

# 7. Soft Obfuscation

A second obfuscation representation is generated with a softened
boundary.

This is useful when a model performs better with a gradual
transition between the visible editing area and the obscured area.

The transition is controlled by the feather radius.

The application should allow the user to change this value.


---

# 8. Why Multiple Representations Exist

Different external image systems may interpret image-editing inputs
differently.

The application therefore does not assume that one representation
will be ideal for every model.

Current representations:

1. Standard grayscale mask.
2. White/blur obfuscated image.
3. Soft white/blur obfuscated image.

Future representations may be added without changing the core
workflow.

Examples could include:

- binary mask,
- alpha mask,
- inverted mask,
- differently feathered mask,
- model-specific image packaging.

The application should remain model-agnostic.


---

# 9. External Image Models

The server does not directly execute:

- Flux
- Flux Krea
- Flux 2
- Qwen Image
- GPT Image
- Gemini
- Nano Banana
- Z Image
- Stable Diffusion
- or any other image-generation model.

These models are external to this project.

The user can download an appropriate representation, send it to
the external system, receive the edited image, and upload that
result back into this application.


---

# 10. External Result Requirements

When the edited result is returned from an external model, the
application should treat it as an untrusted replacement image.

It must NOT automatically replace the original.

The user must explicitly click:

    Merge Edited Region

Only then should the replacement region be composited with the
original.


---

# 11. Merge Algorithm

The merge operation is conceptually:

    final = edited * mask + original * (1 - mask)

Where:

    original = untouched source image
    edited   = external model result
    mask     = canonical grayscale mask

This means:

    mask = 100% white
        -> take edited pixels

    mask = 100% black
        -> retain original pixels

    mask = gray
        -> blend the two


The merge must occur at the original image resolution.


---

# 12. Resolution

The original image resolution must be preserved.

Example:

    Original:
    4096 × 4096

The canonical mask must be:

    4096 × 4096

The external result is resized to the original dimensions if
necessary before merging.

The final merged image must be:

    4096 × 4096


---

# 13. Feathering

Feathering is used to avoid obvious hard edges around the edited
region.

It must only affect the merge mask.

It must NOT modify the original source image.

It must NOT permanently modify the canonical mask.

Conceptually:

    canonical mask
          |
          v
    feathered copy
          |
          v
       merge


The canonical mask remains unchanged.


---

# 14. Source Protection

The following rule is critical:

    NEVER destroy the original image.

The application should maintain:

    original_state
    mask_state

The externally returned image is stored separately.

Example:

    original_state
        |
        +----> mask
        |
        +----> external result
        |
        +----> merged result


The original must remain available until the user intentionally
starts another workflow or clears the workspace.


---

# 15. Failure Handling

If mask creation fails:

    Do not modify the original.

If the external result is missing:

    Do not perform a merge.

If the external result has a different resolution:

    Resize a copy of the external result.

If the mask has a different resolution:

    Resize a copy of the mask.

If the mask contains no painted region:

    Reject the merge.

If the user clears the workspace:

    All temporary state may be discarded.


---

# 16. No Model Dependencies

The first version deliberately avoids:

- PyTorch
- CUDA
- Transformers
- Diffusers
- ONNX
- model weights
- ComfyUI
- Automatic1111
- GPU drivers

The project is intended to run on a small CPU server.

The server's main workload is:

    image manipulation
    mask processing
    PNG encoding
    image compositing


---

# 17. Gradio

Gradio is the UI layer.

The first version uses Gradio because its image editing interface
already provides the interactive painting functionality required by
the project.

The UI is not considered the core of the system.

The underlying operations are:

    create_mask()
    create_obfuscated_image()
    feather_mask()
    merge_external_result()


If another UI is used in the future, these operations should remain
usable independently of the UI.


---

# 18. Project Philosophy

Keep the project small.

Do not introduce a dependency simply because another framework can
perform the same operation.

Do not add ComfyUI merely to reproduce functionality that can be
performed directly with Python libraries.

Do not install an image-generation model on this server unless the
project requirements change explicitly.

The server is a utility service, not an image-generation server.


---

# 19. Future Model Adapters

Model-specific adapters are intentionally NOT required for the
first version.

If later testing demonstrates that a particular external model
requires a special input format, an adapter can be added.

Possible future structure:

    canonical mask
          |
          +--> Flux adapter
          |
          +--> Qwen adapter
          |
          +--> GPT Image adapter
          |
          +--> Gemini adapter
          |
          +--> Other adapter


The canonical mask remains the universal internal representation.


---

# 20. Future Captioning Service

Captioning is a separate future microservice.

It should NOT be mixed into the masking service.

The planned architecture is:

    Mask Service
         |
         v
    Caption Service
         |
         v
    External Image Model


The captioning service can be developed independently after the
masking service is stable.


---

# 21. Server Deployment

The application listens on:

    0.0.0.0:7860

This allows the application to be reached through the server's
network address.

Example:

    http://SERVER_IP:7860


A reverse proxy such as Nginx or Cloudflare can be added later.

The application itself should not depend on the reverse proxy.


---

# 22. GitHub Is the Source of Truth

The complete project should be committed to GitHub.

The server is disposable.

A new server should be able to recreate the application using:

    git clone <repository>

followed by:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python app.py


No irreplaceable application files should exist only on the server.


---

# 23. Initial Project Files

The initial project intentionally contains only:

    app.py
    requirements.txt
    SYSTEM.md
    README.md


Do not split the application into unnecessary modules during the
initial implementation.

Additional files should only be introduced when there is a
demonstrated reason to do so.


---

# 24. Definition of Done

Version 1 is considered functional when the user can:

1. Open the Gradio application.
2. Upload an image.
3. Paint a region.
4. Generate a canonical mask.
5. Generate the obfuscated representation.
6. Generate the soft obfuscated representation.
7. Download/use the appropriate representation externally.
8. Receive an edited image from an external model.
9. Upload that edited image.
10. Merge it with the original.
11. Receive a final image where only the selected region has changed.
12. Verify that the original image remained intact throughout the
    workflow.


---

# 25. Important Principle

The mask is not an instruction to the image model.

It is a boundary.

The external model may generate whatever it generates inside that
boundary.

This application is responsible for ensuring that the resulting
image is merged back into the original only where the user
authorized an edit.

That separation is fundamental to the design.
