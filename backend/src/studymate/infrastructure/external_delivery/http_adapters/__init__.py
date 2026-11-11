"""Provider HTTP adapters; destination registration/resources remain composition-owned."""

from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    TelegramConfig as TelegramConfig,
)
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    UmamiConfig as UmamiConfig,
)
from studymate.infrastructure.external_delivery.http_adapters.configuration import (
    target_fingerprint as target_fingerprint,
)
from studymate.infrastructure.external_delivery.http_adapters.sender import (
    ExternalHttpSender as ExternalHttpSender,
)
