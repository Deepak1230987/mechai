"""Documentation layer — industrial PDF reports & manufacturing packets (Phase C)."""

from .pdf_generator import generate_industrial_pdf, IndustrialPDFConfig
from .machining_packet_builder import build_machining_packet, MachiningPacket

__all__ = [
    "generate_industrial_pdf",
    "IndustrialPDFConfig",
    "build_machining_packet",
    "MachiningPacket",
]
