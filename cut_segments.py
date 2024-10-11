import os
import re
import sys
from pydub import AudioSegment

def convert_time_to_seconds(time_str):
    """
    Convert a time string formatted as HH:MM:SS or MM:SS or SS to total seconds.
    Supports fractional seconds (e.g., "00:01:30.500").
    """
    parts = time_str.split(':')
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = parts
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = parts[0]
        else:
            raise ValueError(f"Invalid time format: {time_str}")

        total_seconds = (
            int(hours) * 3600 +
            int(minutes) * 60 +
            float(seconds)
        )
        return total_seconds
    except ValueError as ve:
        print(f"Error parsing time '{time_str}': {ve}")
        sys.exit(1)

def parse_segments(segments_file_path):
    """
    Parse the segments.txt file and return a dictionary mapping filenames to split points.
    Each key is a filename, and the value is a sorted list of split points in milliseconds.
    """
    segments_dict = {}
    with open(segments_file_path, 'r') as f:
        lines = f.readlines()
        for i in range(0, len(lines), 6):
            header = lines[i].strip()
            filename_match = re.match(r'\[(.*?)\]', header)
            if filename_match:
                filename = filename_match.group(1)
                timestamps = []
                for j in range(1, 6):
                    if i + j >= len(lines):
                        print(f"Unexpected end of file while parsing {filename}.")
                        sys.exit(1)
                    time_range = lines[i + j].strip()
                    if '-' not in time_range:
                        print(f"Invalid time range format in {filename}: '{time_range}'")
                        sys.exit(1)
                    start, end = time_range.split('-')
                    start_sec = convert_time_to_seconds(start)
                    end_sec = convert_time_to_seconds(end)
                    # Convert to milliseconds for pydub
                    timestamps.extend([start_sec * 1000, end_sec * 1000])
                # Remove the first and last timestamps (overall start and end)
                if len(timestamps) < 2:
                    print(f"Not enough timestamps for {filename}.")
                    continue
                split_points = sorted(timestamps[1:-1])
                segments_dict[filename] = split_points
    return segments_dict

def split_audio(input_dir, output_dir, segments_dict):
    """
    Split WAV files based on split points and save the segments.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for filename, split_points in segments_dict.items():
        input_path = os.path.join(input_dir, filename)
        input_path = f'{input_path}.wav'
        if not os.path.isfile(input_path):
            print(f"Input file not found: {input_path}")
            continue

        try:
            audio = AudioSegment.from_wav(input_path)
        except Exception as e:
            print(f"Error loading {input_path}: {e}")
            continue

        # Initialize split points with start and end
        split_points = [0] + split_points + [len(audio)]
        segments = []
        for idx in range(len(split_points) - 1):
            start_ms = split_points[idx]
            end_ms = split_points[idx + 1]
            segment = audio[start_ms:end_ms]
            segments.append(segment)

        # Save segments
        base_filename = os.path.splitext(filename)[0]
        for idx, segment in enumerate(segments, start=1):
            output_filename = f"{base_filename}_segment_{idx}.wav"
            output_path = os.path.join(output_dir, output_filename)
            try:
                segment.export(output_path, format="wav")
                print(f"Saved segment: {output_path}")
            except Exception as e:
                print(f"Error saving {output_path}: {e}")

def main():
    input_dir = 'input'
    output_dir = 'output'
    segments_file = os.path.join(input_dir, 'segments.txt')

    if not os.path.isfile(segments_file):
        print(f"Segments file not found: {segments_file}")
        sys.exit(1)

    segments_dict = parse_segments(segments_file)
    if not segments_dict:
        print("No segments found to process.")
        sys.exit(0)

    split_audio(input_dir, output_dir, segments_dict)
    print("Audio splitting completed.")

if __name__ == "__main__":
    main()

