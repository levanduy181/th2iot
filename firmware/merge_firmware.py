from os.path import join
import subprocess

Import("env")


def merge_firmware(source, target, env):
    build_dir = env.subst("$BUILD_DIR")
    python = env.subst("$PYTHONEXE")
    platform = env.PioPlatform()

    esptool = join(platform.get_package_dir("tool-esptoolpy"), "esptool.py")
    framework = platform.get_package_dir("framework-arduinoespressif32")
    boot_app0 = join(framework, "tools", "partitions", "boot_app0.bin")
    output = join(build_dir, "firmware-merged.bin")

    subprocess.check_call([
        python,
        esptool,
        "--chip",
        "esp32",
        "merge_bin",
        "-o",
        output,
        "--flash_mode",
        "dio",
        "--flash_freq",
        "40m",
        "--flash_size",
        "4MB",
        "0x1000",
        join(build_dir, "bootloader.bin"),
        "0x8000",
        join(build_dir, "partitions.bin"),
        "0xe000",
        boot_app0,
        "0x10000",
        join(build_dir, "firmware.bin"),
    ])


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", merge_firmware)
