import io
from pathlib import Path

import gradio as gr
import numpy as np
from PIL import Image, ImageFilter, ImageOps


APP_TITLE = "Universal Image Mask Tool"
MAX_IMAGE_PIXELS = 100_000_000

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


# ============================================================
# Image utilities
# ============================================================

def load_image(image):
    """Convert Gradio/PIL input into a safe RGB PIL image."""
    if image is None:
        return None

    if isinstance(image, Image.Image):
        return image.convert("RGB")

    return Image.open(image).convert("RGB")


def normalize_mask(mask, size):
    """
    Convert any supplied mask into a grayscale L image
    matching the original image resolution.
    """
    if mask is None:
        return Image.new("L", size, 0)

    if not isinstance(mask, Image.Image):
        mask = Image.fromarray(np.asarray(mask))

    mask = mask.convert("L")

    if mask.size != size:
        mask = mask.resize(size, Image.Resampling.LANCZOS)

    return mask


# ============================================================
# Mask generation
# ============================================================

def extract_editor_mask(editor_data, original_size):
    """
    Extract the user's painted mask from Gradio ImageEditor data.

    Gradio can return an ImageEditor value containing:
        background
        layers
        composite

    We preferentially use the layer containing the user's drawing.
    """
    if editor_data is None:
        raise ValueError("Please upload an image and paint a mask first.")

    # Older/simple Gradio configurations may return a PIL image.
    if isinstance(editor_data, Image.Image):
        return normalize_mask(editor_data, original_size)

    if not isinstance(editor_data, dict):
        raise ValueError("Unsupported ImageEditor data format.")

    layers = editor_data.get("layers") or []

    if layers:
        # The last layer is normally the user's most recent drawing.
        for layer in reversed(layers):
            if layer is None:
                continue

            if isinstance(layer, Image.Image):
                layer = layer.convert("RGBA")

                alpha = layer.getchannel("A")

                # Use alpha where available.
                if alpha.getbbox():
                    return normalize_mask(alpha, original_size)

                # Otherwise derive visibility from RGB.
                rgb = np.asarray(layer.convert("RGB"))
                gray = np.max(rgb, axis=2)
                return normalize_mask(
                    Image.fromarray(gray.astype(np.uint8)),
                    original_size,
                )

    composite = editor_data.get("composite")

    if isinstance(composite, Image.Image):
        return normalize_mask(composite, original_size)

    raise ValueError("No painted mask was found.")


def clean_mask(mask, threshold=8):
    """
    Remove extremely weak brush pixels/noise while preserving
    antialiased edges.
    """
    arr = np.asarray(mask.convert("L")).astype(np.uint8)

    arr[arr < threshold] = 0

    return Image.fromarray(arr, mode="L")


def feather_mask(mask, radius=8):
    """
    Create a soft transition around the selected region.
    This is useful when the edited result will later be merged
    back into the pristine source image.
    """
    radius = max(0, int(radius))

    if radius == 0:
        return mask.convert("L")

    return mask.convert("L").filter(
        ImageFilter.GaussianBlur(radius=radius)
    )


# ============================================================
# Obfuscation
# ============================================================

def create_obfuscated_image(original, mask, strength=0.92):
    """
    Create the white/mist-style image representation.

    The selected region remains visible.

    Everything outside the selected region is progressively
    washed toward white, reducing the amount of visual
    information available to an external image-edit model.

    This is NOT the authoritative merge mask. The original
    grayscale mask remains the source of truth.
    """
    original = original.convert("RGB")
    mask = mask.convert("L")

    strength = max(0.0, min(1.0, float(strength)))

    # Blur the unselected information before washing it toward white.
    blurred = original.filter(ImageFilter.GaussianBlur(radius=18))

    white = Image.new("RGB", original.size, (255, 255, 255))

    # Build an obfuscation layer.
    blurred_arr = np.asarray(blurred).astype(np.float32)
    white_arr = np.asarray(white).astype(np.float32)

    washed_arr = (
        blurred_arr * (1.0 - strength)
        + white_arr * strength
    ).clip(0, 255).astype(np.uint8)

    washed = Image.fromarray(washed_arr, mode="RGB")

    # Preserve the selected region.
    return Image.composite(
        original,
        washed,
        mask,
    )


def create_soft_obfuscation(original, mask, feather=12, strength=0.92):
    """
    Same concept as the standard obfuscation image, but with a
    softened transition around the editable region.
    """
    soft_mask = feather_mask(mask, feather)

    return create_obfuscated_image(
        original,
        soft_mask,
        strength=strength,
    )


# ============================================================
# Mask creation pipeline
# ============================================================

def generate_masks(editor_data, feather_radius, obfuscation_strength):
    """
    Main mask-generation operation.

    Returns:
        original
        normal mask
        obfuscated image
        soft obfuscated image
        status
    """
    if editor_data is None:
        raise gr.Error("Upload an image and paint the region you want to edit.")

    background = editor_data.get("background")

    if background is None:
        raise gr.Error("No source image was found.")

    original = load_image(background)

    if original is None:
        raise gr.Error("Could not load the source image.")

    try:
        mask = extract_editor_mask(
            editor_data,
            original.size,
        )
    except Exception as exc:
        raise gr.Error(str(exc))

    mask = clean_mask(mask)

    if mask.getbbox() is None:
        raise gr.Error(
            "No painted region was detected. Paint over the area you want "
            "the external image model to edit."
        )

    obfuscated = create_obfuscated_image(
        original,
        mask,
        obfuscation_strength,
    )

    soft_obfuscated = create_soft_obfuscation(
        original,
        mask,
        feather_radius,
        obfuscation_strength,
    )

    return (
        original,
        mask,
        obfuscated,
        soft_obfuscated,
        "Mask created successfully. The original image is preserved.",
    )


# ============================================================
# Merge
# ============================================================

def merge_external_result(original, edited, mask, feather_radius):
    """
    Merge an externally generated/edited image back into the
    untouched original.

    Only the masked region is taken from the external result.
    """
    if original is None:
        raise gr.Error("The original image is missing.")

    if edited is None:
        raise gr.Error(
            "Upload the edited image returned by your external image model."
        )

    if mask is None:
        raise gr.Error("The mask is missing.")

    original = load_image(original)
    edited = load_image(edited)

    mask = normalize_mask(mask, original.size)

    if edited.size != original.size:
        edited = edited.resize(
            original.size,
            Image.Resampling.LANCZOS,
        )

    # Slight feathering prevents a hard rectangular/paint-edge seam.
    merge_mask = feather_mask(
        mask,
        feather_radius,
    )

    merged = Image.composite(
        edited,
        original,
        merge_mask,
    )

    return merged


# ============================================================
# Reset
# ============================================================

def reset_workspace():
    return (
        None,  # editor
        None,  # original
        None,  # mask
        None,  # obfuscated
        None,  # soft obfuscated
        None,  # edited result
        None,  # merged result
        "Workspace cleared.",
    )


# ============================================================
# UI
# ============================================================

with gr.Blocks(
    title=APP_TITLE,
) as demo:

    gr.Markdown(
        """
# Universal Image Mask Tool

Upload an image, paint the region that needs editing, and generate
multiple mask representations.

The original image remains untouched until you explicitly merge
an externally edited result back into it.
"""
    )

    with gr.Row():

        with gr.Column(scale=1):

            editor = gr.ImageEditor(
                label="1. Paint the Region to Edit",
                type="pil",
                image_mode="RGBA",
                sources=["upload"],
                brush=gr.Brush(
                    colors=["#FFFFFF"],
                    default_size=32,
                ),
                height=600,
            )

            with gr.Row():
                feather_slider = gr.Slider(
                    minimum=0,
                    maximum=32,
                    value=8,
                    step=1,
                    label="Merge Feather",
                )

                obfuscation_slider = gr.Slider(
                    minimum=0.50,
                    maximum=1.00,
                    value=0.92,
                    step=0.01,
                    label="Obfuscation Strength",
                )

            generate_button = gr.Button(
                "Generate Masks",
                variant="primary",
            )

        with gr.Column(scale=1):

            original_preview = gr.Image(
                label="Original — Locked Source",
                type="pil",
            )

            mask_preview = gr.Image(
                label="Mask — Grayscale",
                type="pil",
            )

            mask_download = gr.DownloadButton(
                "Download Grayscale Mask",
            )

    gr.Markdown("## Generated Mask Representations")

    with gr.Row():

        with gr.Column():
            gr.Markdown("### Mask A — Standard")

            standard_mask_preview = gr.Image(
                label="Standard Mask",
                type="pil",
            )

        with gr.Column():
            gr.Markdown("### Mask B — White Obfuscation")

            obfuscation_preview = gr.Image(
                label="Obfuscated Image",
                type="pil",
            )

        with gr.Column():
            gr.Markdown("### Mask C — Soft Obfuscation")

            soft_obfuscation_preview = gr.Image(
                label="Soft Obfuscated Image",
                type="pil",
            )

    status = gr.Markdown(
        "Waiting for an image."
    )

    gr.Markdown("---")

    gr.Markdown(
        """
## External Editing

Download the appropriate representation and send it to your
external image-editing model.

When the edited image comes back, upload it below.
"""
    )

    edited_result = gr.Image(
        label="2. Upload External Edited Result",
        type="pil",
    )

    merge_button = gr.Button(
        "Merge Edited Region",
        variant="primary",
    )

    merged_result = gr.Image(
        label="3. Final Merged Image",
        type="pil",
    )

    with gr.Row():

        clear_button = gr.Button(
            "Clear Workspace",
        )

    # Hidden state used as the authoritative source of truth.
    original_state = gr.State()
    mask_state = gr.State()

    generate_button.click(
        fn=generate_masks,
        inputs=[
            editor,
            feather_slider,
            obfuscation_slider,
        ],
        outputs=[
            original_state,
            mask_state,
            original_preview,
            standard_mask_preview,
            obfuscation_preview,
            soft_obfuscation_preview,
            status,
        ],
    )

    merge_button.click(
        fn=merge_external_result,
        inputs=[
            original_state,
            edited_result,
            mask_state,
            feather_slider,
        ],
        outputs=[
            merged_result,
        ],
    )

    clear_button.click(
        fn=reset_workspace,
        inputs=[],
        outputs=[
            editor,
            original_state,
            mask_state,
            standard_mask_preview,
            obfuscation_preview,
            soft_obfuscation_preview,
            edited_result,
            merged_result,
            status,
        ],
    )

    # Downloadable standard mask.
    def prepare_mask_download(mask):
        if mask is None:
            return None

        buffer = io.BytesIO()
        mask.save(buffer, format="PNG")
        buffer.seek(0)

        return gr.File(
            value=buffer,
            visible=True,
        )

    mask_download.click(
        fn=prepare_mask_download,
        inputs=[mask_state],
        outputs=[],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
                  )
