import math


def reporter_factor(unique_reporters: int, saturation: int = 30) -> float:
    if type(unique_reporters) is not int or unique_reporters < 0:
        raise ValueError("Eligible reporter count must be a nonnegative integer")
    if type(saturation) is not int or saturation < 1:
        raise ValueError("Reporter saturation must be a positive integer")
    # Avoid converting arbitrarily large integer counts to floating point before saturation.
    return (
        10.0
        if unique_reporters >= saturation
        else 10 * math.log1p(unique_reporters) / math.log1p(saturation)
    )
