import os
import time
import math
import argparse
import subprocess
import tempfile
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import convert_mp3

def run_inference(file_path):
    try:
        result = subprocess.run(['python', 'main.py', '--mode', 'infer', '--file', file_path], capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        if 'A' in output:
            return 'A'
        elif 'B' in output:
            return 'B'
        else:
            print(f'Error: Unexpected inference output for {file_path}')
            return None
    except subprocess.CalledProcessError as e:
        print(f'Error running inference on {file_path}: {e}')
        return None

#Processes a single audio chunk: saves it temporarily, runs inference, and deletes the temp file.
def process_chunk(chunk_index, chunk):
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        chunk.export(temp_file.name, format='wav')
        temp_file_path = temp_file.name
    predicted_class = run_inference(temp_file_path)
    os.remove(temp_file_path)
    return (chunk_index, predicted_class)

#Applies a heuristic to correct misclassifications and enforce the expected segment pattern.
def apply_forgiving_heuristic(predictions, min_surround_chunks=3, max_flip_length=2):
    # Step 1: Group consecutive identical labels into segments
    segments = []
    current_label = predictions[0]
    current_indices = [0]
    for i in range(1, len(predictions)):
        if predictions[i] == current_label:
            current_indices.append(i)
        else:
            segments.append((current_label, current_indices))
            current_label = predictions[i]
            current_indices = [i]
    segments.append((current_label, current_indices))  # Add the last segment
    # Step 2: Iterate through segments to find and flip misclassifications
    for i in range(1, len(segments) - 1):
        label, indices = segments[i]
        prev_label, prev_indices = segments[i - 1]
        next_label, next_indices = segments[i + 1]
        # Check if the current segment is short and surrounded by opposite types
        if len(indices) <= max_flip_length and prev_label != label and next_label != label:
            # Check if surrounding segments have enough chunks
            if len(prev_indices) >= min_surround_chunks and len(next_indices) >= min_surround_chunks:
                # Flip the label
                new_label = 'B' if label == 'A' else 'A'
                print(f"Flipping from {label} to {new_label}: Chunks {indices[0]+1}-{indices[-1]+1}")
                segments[i] = (new_label, indices)
    # Step 3: Reconstruct the corrected predictions list
    corrected_predictions = []
    for label, indices in segments:
        for _ in indices:
            corrected_predictions.append(label)
    return corrected_predictions

def reconstruct_audio(corrected_predictions, chunks, desired_label='B'):
    episode_number = time.strftime("%d-%H%M")
    def get_dir(folder):
        return os.path.join('export', episode_number, folder)
    type_dirs = {'A': get_dir('A'), 'B': get_dir('B')}
    for dir_path in type_dirs.values():
        os.makedirs(dir_path, exist_ok=True)
    combined_audio = None
    for i, chunk in enumerate(chunks):
        label = corrected_predictions[i]
        if label == desired_label:
            if combined_audio is None:
                combined_audio = chunk
            else:
                combined_audio += chunk
        if label in type_dirs:
            chunk_filename = f"chunk_{i}_{label}.wav"
            chunk_path = os.path.join(type_dirs[label], chunk_filename)
            chunk.export(chunk_path, format="wav")
    return combined_audio

#Processes the input audio file by removing segments classified as type A and combining the remaining type B segments into a new audio file.
def process_audio(input_file, chunk_length_sec=10):
    try:
        audio = AudioSegment.from_wav(input_file)
    except Exception as e:
        print(f'Error loading audio file {input_file}: {e}')
        return
    total_length_ms = len(audio)
    chunk_length_ms = chunk_length_sec * 1000
    num_chunks = total_length_ms // chunk_length_ms
    num_chunks = int(num_chunks)
    filename, file_extension = os.path.splitext(input_file)
    output_file = f'{filename}_cut{file_extension}'
    print(f'\nProcessing Audio File: {input_file}')
    print(f'Total Length: {total_length_ms / 1000:.2f} seconds')
    print(f'Chunk Length: {chunk_length_sec} seconds')
    print(f'Number of Full Chunks: {num_chunks}\n')
    chunks = []
    for i in range(num_chunks):
        start_ms = i * chunk_length_ms
        end_ms = start_ms + chunk_length_ms
        chunk = audio[start_ms:end_ms]
        chunks.append(chunk)
    #Classify chunks in parallel
    predictions = [None] * num_chunks
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_chunk, i, chunk): i for i, chunk in enumerate(chunks)}
        with open('list.txt', 'a') as f:
            for future in as_completed(futures):
                chunk_index, predicted_class = future.result()
                predictions[chunk_index] = predicted_class
                print(f'Chunk {chunk_index + 1:03}/{num_chunks}: Classified as {predicted_class}')
                f.write(f'{chunk_index + 1:03}: {predicted_class}\n')
    #Apply the forgiving heuristic
    corrected_predictions = apply_forgiving_heuristic(predictions)
    #Reconstruct the final audio
    combined_audio = reconstruct_audio(corrected_predictions, chunks, desired_label='B')
    if combined_audio:
        try:
            combined_audio.export(output_file, format='wav')
            print(f'\nCombined type B audio saved')
        except Exception as e:
            print(f'Error saving combined audio: {e}')
    else:
        print('\nNo type B segments found after applying heuristic.')

def process_file(wav_path):
    if not os.path.isfile(wav_path):
        print(f'Input file {wav_path} given to process_file does not exist.')
        return
    process_audio(wav_path) #should convert if mp3

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Input file path')
    args = parser.parse_args()
    process_file(args.file)

