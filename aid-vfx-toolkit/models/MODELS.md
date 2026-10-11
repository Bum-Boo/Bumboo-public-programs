# External model acquisition

No model files are distributed. Depth uses the ONNX Community conversion of Depth Anything V2 Small: https://huggingface.co/onnx-community/depth-anything-v2-small . Landmark models use Google MediaPipe model storage URLs declared in track/track.py. Review model-specific license terms before download or use; model redistribution rights are not asserted here.

The original scripts download mutable upstream files without a pinned checksum. For repeatable runs, pre-download reviewed files into models/, record their SHA256 locally and compare before running. This release does not claim reproducible or authenticated model weights. Avoid redistributing downloaded bundles until their specific terms are established.
