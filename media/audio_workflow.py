import os
import random
import sys
import json
import argparse
import contextlib
from typing import Sequence, Mapping, Any, Union
import torch


def get_value_at_index(obj: Union[Sequence, Mapping], index: int) -> Any:
    """Returns the value at the given index of a sequence or mapping.

    If the object is a sequence (like list or string), returns the value at the given index.
    If the object is a mapping (like a dictionary), returns the value at the index-th key.

    Some return a dictionary, in these cases, we look for the "results" key

    Args:
        obj (Union[Sequence, Mapping]): The object to retrieve the value from.
        index (int): The index of the value to retrieve.

    Returns:
        Any: The value at the given index.

    Raises:
        IndexError: If the index is out of bounds for the object and the object is not a mapping.
    """
    try:
        return obj[index]
    except KeyError:
        return obj["result"][index]


def find_path(name: str, path: str = None) -> str:
    """
    Recursively looks at parent folders starting from the given path until it finds the given name.
    Returns the path as a Path object if found, or None otherwise.
    """
    # If no path is given, use the current working directory
    if path is None:
        if args is None or args.comfyui_directory is None:
            path = os.getcwd()
        else:
            path = args.comfyui_directory

    # Check if the current directory contains the name
    if name in os.listdir(path):
        path_name = os.path.join(path, name)
        print(f"{name} found: {path_name}")
        return path_name

    # Get the parent directory
    parent_directory = os.path.dirname(path)

    # If the parent directory is the same as the current directory, we've reached the root and stop the search
    if parent_directory == path:
        return None

    # Recursively call the function with the parent directory
    return find_path(name, parent_directory)


def add_comfyui_directory_to_sys_path() -> None:
    """
    Add 'ComfyUI' to the sys.path
    """
    comfyui_path = find_path("ComfyUI")
    if comfyui_path is not None and os.path.isdir(comfyui_path):
        sys.path.append(comfyui_path)

        manager_path = os.path.join(
            comfyui_path, "custom_nodes", "ComfyUI-Manager", "glob"
        )

        if os.path.isdir(manager_path) and os.listdir(manager_path):
            sys.path.append(manager_path)
            global has_manager
            has_manager = True

        import __main__

        if getattr(__main__, "__file__", None) is None:
            __main__.__file__ = os.path.join(comfyui_path, "main.py")

        print(f"'{comfyui_path}' added to sys.path")


def add_extra_model_paths() -> None:
    """
    Parse the optional extra_model_paths.yaml file and add the parsed paths to the sys.path.
    """
    from comfy.options import enable_args_parsing

    enable_args_parsing()
    from utils.extra_config import load_extra_path_config

    extra_model_paths = find_path("extra_model_paths.yaml")

    if extra_model_paths is not None:
        load_extra_path_config(extra_model_paths)
    else:
        print("Could not find the extra_model_paths config file.")


def import_custom_nodes() -> None:
    """Find all custom nodes in the custom_nodes folder and add those node objects to NODE_CLASS_MAPPINGS

    This function sets up a new asyncio event loop, initializes the PromptServer,
    creates a PromptQueue, and initializes the custom nodes.
    """
    if has_manager:
        try:
            import manager_core as manager
        except ImportError:
            print("Could not import manager_core, proceeding without it.")
            return
        else:
            if hasattr(manager, "get_config"):
                print("Patching manager_core.get_config to enforce offline mode.")
                try:
                    get_config = manager.get_config

                    def _get_config(*args, **kwargs):
                        config = get_config(*args, **kwargs)
                        config["network_mode"] = "offline"
                        return config

                    manager.get_config = _get_config
                except Exception as e:
                    print("Failed to patch manager_core.get_config:", e)

    import asyncio
    import execution
    from nodes import init_extra_nodes
    import server

    # Creating a new event loop and setting it as the default loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def inner():
        # Creating an instance of PromptServer with the loop
        server_instance = server.PromptServer(loop)
        execution.PromptQueue(server_instance)

        # Initializing custom nodes
        await init_extra_nodes(init_custom_nodes=True)

    loop.run_until_complete(inner())


def save_image_wrapper(context, cls):
    if args.output is None:
        return cls

    from PIL import Image, ImageOps, ImageSequence
    from PIL.PngImagePlugin import PngInfo

    import numpy as np

    class WrappedSaveImage(cls):
        counter = 0

        def save_images(
            self, images, filename_prefix="ComfyUI", prompt=None, extra_pnginfo=None
        ):
            if args.output is None:
                return super().save_images(
                    images, filename_prefix, prompt, extra_pnginfo
                )
            else:
                if len(images) > 1 and args.output == "-":
                    raise ValueError("Cannot save multiple images to stdout")
                filename_prefix += self.prefix_append

                results = list()
                for batch_number, image in enumerate(images):
                    i = 255.0 * image.cpu().numpy()
                    img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
                    metadata = None
                    if not args.disable_metadata:
                        metadata = PngInfo()
                        if prompt is not None:
                            metadata.add_text("prompt", json.dumps(prompt))
                        if extra_pnginfo is not None:
                            for x in extra_pnginfo:
                                metadata.add_text(x, json.dumps(extra_pnginfo[x]))

                    if args.output == "-":
                        # Hack to briefly restore stdout
                        if context is not None:
                            context.__exit__(None, None, None)
                        try:
                            img.save(
                                sys.stdout.buffer,
                                format="png",
                                pnginfo=metadata,
                                compress_level=self.compress_level,
                            )
                        finally:
                            if context is not None:
                                context.__enter__()
                    else:
                        subfolder = ""
                        if len(images) == 1:
                            if os.path.isdir(args.output):
                                subfolder = args.output
                                file = "output.png"
                            else:
                                subfolder, file = os.path.split(args.output)
                                if subfolder == "":
                                    subfolder = os.getcwd()
                        else:
                            if os.path.isdir(args.output):
                                subfolder = args.output
                                file = filename_prefix
                            else:
                                subfolder, file = os.path.split(args.output)

                            if subfolder == "":
                                subfolder = os.getcwd()

                            files = os.listdir(subfolder)
                            file_pattern = file
                            while True:
                                filename_with_batch_num = file_pattern.replace(
                                    "%batch_num%", str(batch_number)
                                )
                                file = (
                                    f"{filename_with_batch_num}_{self.counter:05}.png"
                                )
                                self.counter += 1

                                if file not in files:
                                    break

                        img.save(
                            os.path.join(subfolder, file),
                            pnginfo=metadata,
                            compress_level=self.compress_level,
                        )
                        print("Saved image to", os.path.join(subfolder, file))
                        results.append(
                            {
                                "filename": file,
                                "subfolder": subfolder,
                                "type": self.type,
                            }
                        )

                return {"ui": {"images": results}}

    return WrappedSaveImage


def parse_arg(s: Any, default: Any = None) -> Any:
    """Parses a JSON string, returning it unchanged if the parsing fails."""
    if __name__ == "__main__" or not isinstance(s, str):
        return s

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return s


parser = argparse.ArgumentParser(
    description="A converted ComfyUI workflow. Node inputs listed below. Values passed should be valid JSON (assumes string if not valid JSON)."
)
parser.add_argument(
    "--seconds1",
    default=240,
    help='Argument 0, input `seconds` for node "EmptyAceStepLatentAudio" id 17 (autogenerated)',
)

parser.add_argument(
    "--batch_size2",
    default=1,
    help='Argument 1, input `batch_size` for node "EmptyAceStepLatentAudio" id 17 (autogenerated)',
)

parser.add_argument(
    "--ckpt_name3",
    default="ace_step_v1_3.5b.safetensors",
    help='Argument 0, input `ckpt_name` for node "Load Checkpoint" id 40 (autogenerated)',
)

parser.add_argument(
    "--multiplier4",
    default=1.0000000000000002,
    help='Argument 0, input `multiplier` for node "LatentOperationTonemapReinhard" id 50 (autogenerated)',
)

parser.add_argument(
    "--tags5",
    default="anime, soft female vocals, kawaii pop, j-pop, childish, piano, guitar, synthesizer, fast, happy, cheerful, lighthearted\t\n",
    help='Argument 1, input `tags` for node "TextEncodeAceStepAudio" id 14 (autogenerated)',
)

parser.add_argument(
    "--lyrics6",
    default="\n\n",
    help='Argument 2, input `lyrics` for node "TextEncodeAceStepAudio" id 14 (autogenerated)',
)

parser.add_argument(
    "--lyrics_strength7",
    default=0.9900000000000002,
    help='Argument 3, input `lyrics_strength` for node "TextEncodeAceStepAudio" id 14 (autogenerated)',
)

parser.add_argument(
    "--shift8",
    default=5.000000000000001,
    help='Argument 1, input `shift` for node "ModelSamplingSD3" id 51 (autogenerated)',
)

parser.add_argument(
    "--seed9",
    default=468254064217846,
    help='Argument 1, input `seed` for node "KSampler" id 52 (autogenerated)',
)

parser.add_argument(
    "--steps10",
    default=50,
    help='Argument 2, input `steps` for node "KSampler" id 52 (autogenerated)',
)

parser.add_argument(
    "--cfg11",
    default=5,
    help='Argument 3, input `cfg` for node "KSampler" id 52 (autogenerated)',
)

parser.add_argument(
    "--sampler_name12",
    default="euler",
    help='Argument 4, input `sampler_name` for node "KSampler" id 52 (autogenerated)',
)

parser.add_argument(
    "--scheduler13",
    default="simple",
    help='Argument 5, input `scheduler` for node "KSampler" id 52 (autogenerated)',
)

parser.add_argument(
    "--denoise14",
    default=1,
    help='Argument 9, input `denoise` for node "KSampler" id 52 (autogenerated)',
)

parser.add_argument(
    "--filename_prefix15",
    default="GeneratedAudio_",
    help='Argument 1, input `filename_prefix` for node "Save Audio (MP3)" id 59 (autogenerated)',
)

parser.add_argument(
    "--quality16",
    default="V0",
    help='Argument 2, input `quality` for node "Save Audio (MP3)" id 59 (autogenerated)',
)

parser.add_argument(
    "--queue-size",
    "-q",
    type=int,
    default=1,
    help="How many times the workflow will be executed (default: 1)",
)

parser.add_argument(
    "--comfyui-directory",
    "-c",
    default=None,
    help="Where to look for ComfyUI (default: current directory)",
)

parser.add_argument(
    "--output",
    "-o",
    default=None,
    help="The location to save the output image. Either a file path, a directory, or - for stdout (default: the ComfyUI output directory)",
)

parser.add_argument(
    "--disable-metadata",
    action="store_true",
    help="Disables writing workflow metadata to the outputs",
)


comfy_args = [sys.argv[0]]
if __name__ == "__main__" and "--" in sys.argv:
    idx = sys.argv.index("--")
    comfy_args += sys.argv[idx + 1 :]
    sys.argv = sys.argv[:idx]

args = None
if __name__ == "__main__":
    args = parser.parse_args()
    sys.argv = comfy_args
if args is not None and args.output is not None and args.output == "-":
    ctx = contextlib.redirect_stdout(sys.stderr)
else:
    ctx = contextlib.nullcontext()

PROMPT_DATA = json.loads(
    '{"14": {"inputs": {"tags": "anime, soft female vocals, kawaii pop, j-pop, childish, piano, guitar, synthesizer, fast, happy, cheerful, lighthearted\\t\\n", "lyrics": "\\n\\n", "lyrics_strength": 0.9900000000000002, "clip": ["40", 1]}, "class_type": "TextEncodeAceStepAudio", "_meta": {"title": "TextEncodeAceStepAudio"}}, "17": {"inputs": {"seconds": 240, "batch_size": 1}, "class_type": "EmptyAceStepLatentAudio", "_meta": {"title": "EmptyAceStepLatentAudio"}}, "18": {"inputs": {"samples": ["52", 0], "vae": ["40", 2]}, "class_type": "VAEDecodeAudio", "_meta": {"title": "VAEDecodeAudio"}}, "40": {"inputs": {"ckpt_name": "ace_step_v1_3.5b.safetensors"}, "class_type": "CheckpointLoaderSimple", "_meta": {"title": "Load Checkpoint"}}, "44": {"inputs": {"conditioning": ["14", 0]}, "class_type": "ConditioningZeroOut", "_meta": {"title": "ConditioningZeroOut"}}, "49": {"inputs": {"model": ["51", 0], "operation": ["50", 0]}, "class_type": "LatentApplyOperationCFG", "_meta": {"title": "LatentApplyOperationCFG"}}, "50": {"inputs": {"multiplier": 1.0000000000000002}, "class_type": "LatentOperationTonemapReinhard", "_meta": {"title": "LatentOperationTonemapReinhard"}}, "51": {"inputs": {"shift": 5.000000000000001, "model": ["40", 0]}, "class_type": "ModelSamplingSD3", "_meta": {"title": "ModelSamplingSD3"}}, "52": {"inputs": {"seed": 468254064217846, "steps": 50, "cfg": 5, "sampler_name": "euler", "scheduler": "simple", "denoise": 1, "model": ["49", 0], "positive": ["14", 0], "negative": ["44", 0], "latent_image": ["17", 0]}, "class_type": "KSampler", "_meta": {"title": "KSampler"}}, "59": {"inputs": {"filename_prefix": "GeneratedAudio_", "quality": "V0", "audioUI": "", "audio": ["18", 0]}, "class_type": "SaveAudioMP3", "_meta": {"title": "Save Audio (MP3)"}}}'
)


def import_custom_nodes() -> None:
    """Find all custom nodes in the custom_nodes folder and add those node objects to NODE_CLASS_MAPPINGS

    This function sets up a new asyncio event loop, initializes the PromptServer,
    creates a PromptQueue, and initializes the custom nodes.
    """
    if has_manager:
        try:
            import manager_core as manager
        except ImportError:
            print("Could not import manager_core, proceeding without it.")
            return
        else:
            if hasattr(manager, "get_config"):
                print("Patching manager_core.get_config to enforce offline mode.")
                try:
                    get_config = manager.get_config

                    def _get_config(*args, **kwargs):
                        config = get_config(*args, **kwargs)
                        config["network_mode"] = "offline"
                        return config

                    manager.get_config = _get_config
                except Exception as e:
                    print("Failed to patch manager_core.get_config:", e)

    import asyncio
    import execution
    from nodes import init_extra_nodes
    import server

    # Creating a new event loop and setting it as the default loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def inner():
        # Creating an instance of PromptServer with the loop
        server_instance = server.PromptServer(loop)
        execution.PromptQueue(server_instance)

        # Initializing custom nodes
        await init_extra_nodes(init_custom_nodes=True)

    loop.run_until_complete(inner())


_custom_nodes_imported = False
_custom_path_added = False


def main(*func_args, **func_kwargs):
    global args, _custom_nodes_imported, _custom_path_added
    if __name__ == "__main__":
        if args is None:
            args = parser.parse_args()
    else:
        defaults = dict(
            (arg, parser.get_default(arg))
            for arg in ["queue_size", "comfyui_directory", "output", "disable_metadata"]
            + [
                "seconds1",
                "batch_size2",
                "ckpt_name3",
                "multiplier4",
                "tags5",
                "lyrics6",
                "lyrics_strength7",
                "shift8",
                "seed9",
                "steps10",
                "cfg11",
                "sampler_name12",
                "scheduler13",
                "denoise14",
                "filename_prefix15",
                "quality16",
            ]
        )

        all_args = dict()
        all_args.update(defaults)
        all_args.update(func_kwargs)

        args = argparse.Namespace(**all_args)

    with ctx:
        if not _custom_path_added:
            add_comfyui_directory_to_sys_path()
            add_extra_model_paths()

            _custom_path_added = True

        if not _custom_nodes_imported:
            import_custom_nodes()

            _custom_nodes_imported = True

        from nodes import NODE_CLASS_MAPPINGS

    with torch.inference_mode(), ctx:
        emptyacesteplatentaudio = NODE_CLASS_MAPPINGS["EmptyAceStepLatentAudio"]()
        emptyacesteplatentaudio_17 = emptyacesteplatentaudio.EXECUTE_NORMALIZED(
            seconds=parse_arg(args.seconds1), batch_size=parse_arg(args.batch_size2)
        )

        checkpointloadersimple = NODE_CLASS_MAPPINGS["CheckpointLoaderSimple"]()
        checkpointloadersimple_40 = checkpointloadersimple.load_checkpoint(
            ckpt_name=parse_arg(args.ckpt_name3)
        )

        latentoperationtonemapreinhard = NODE_CLASS_MAPPINGS[
            "LatentOperationTonemapReinhard"
        ]()
        latentoperationtonemapreinhard_50 = (
            latentoperationtonemapreinhard.EXECUTE_NORMALIZED(
                multiplier=parse_arg(args.multiplier4)
            )
        )

        textencodeacestepaudio = NODE_CLASS_MAPPINGS["TextEncodeAceStepAudio"]()
        modelsamplingsd3 = NODE_CLASS_MAPPINGS["ModelSamplingSD3"]()
        latentapplyoperationcfg = NODE_CLASS_MAPPINGS["LatentApplyOperationCFG"]()
        conditioningzeroout = NODE_CLASS_MAPPINGS["ConditioningZeroOut"]()
        ksampler = NODE_CLASS_MAPPINGS["KSampler"]()
        vaedecodeaudio = NODE_CLASS_MAPPINGS["VAEDecodeAudio"]()
        saveaudiomp3 = NODE_CLASS_MAPPINGS["SaveAudioMP3"]()
        for q in range(args.queue_size):
            textencodeacestepaudio_14 = textencodeacestepaudio.EXECUTE_NORMALIZED(
                tags=parse_arg(args.tags5),
                lyrics=parse_arg(args.lyrics6),
                lyrics_strength=parse_arg(args.lyrics_strength7),
                clip=get_value_at_index(checkpointloadersimple_40, 1),
            )

            modelsamplingsd3_51 = modelsamplingsd3.patch(
                shift=parse_arg(args.shift8),
                model=get_value_at_index(checkpointloadersimple_40, 0),
            )

            latentapplyoperationcfg_49 = latentapplyoperationcfg.EXECUTE_NORMALIZED(
                model=get_value_at_index(modelsamplingsd3_51, 0),
                operation=get_value_at_index(latentoperationtonemapreinhard_50, 0),
            )

            conditioningzeroout_44 = conditioningzeroout.zero_out(
                conditioning=get_value_at_index(textencodeacestepaudio_14, 0)
            )

            ksampler_52 = ksampler.sample(
                seed=parse_arg(args.seed9),
                steps=parse_arg(args.steps10),
                cfg=parse_arg(args.cfg11),
                sampler_name=parse_arg(args.sampler_name12),
                scheduler=parse_arg(args.scheduler13),
                denoise=parse_arg(args.denoise14),
                model=get_value_at_index(latentapplyoperationcfg_49, 0),
                positive=get_value_at_index(textencodeacestepaudio_14, 0),
                negative=get_value_at_index(conditioningzeroout_44, 0),
                latent_image=get_value_at_index(emptyacesteplatentaudio_17, 0),
            )

            vaedecodeaudio_18 = vaedecodeaudio.decode(
                samples=get_value_at_index(ksampler_52, 0),
                vae=get_value_at_index(checkpointloadersimple_40, 2),
            )

            saveaudiomp3_59 = saveaudiomp3.save_mp3(
                filename_prefix=parse_arg(args.filename_prefix15),
                quality=parse_arg(args.quality16),
                audio=get_value_at_index(vaedecodeaudio_18, 0),
                prompt=PROMPT_DATA,
            )


if __name__ == "__main__":
    main()
