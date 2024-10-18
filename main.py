import os
import glob
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from torch.utils.data import DataLoader
from utils import AudioDataset, preprocess_audio

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
SAMPLING_RATE = 2000
N_MFCC = 5
HIDDEN_SIZE = 64
NUM_LAYERS = 2
SEQ_LENGTH = 200
EPOCHS = 5 #default, you will be prompted
BATCH_SIZE = 16
LEARNING_RATE = 0.0001
TRAIN_DIR = 'train'
VAL_DIR = 'val'

class AudioClassifier(nn.Module):
    def __init__(self):
        super(AudioClassifier, self).__init__()
        self.lstm = nn.LSTM(input_size=N_MFCC*3, hidden_size=HIDDEN_SIZE, num_layers=NUM_LAYERS, batch_first=True)
        self.fc = nn.Linear(HIDDEN_SIZE, 2)
        self.softmax = nn.LogSoftmax(dim=1)
    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :]
        out = self.fc(out)
        return self.softmax(out)

def train(model, train_loader, criterion, optimizer):
    model.train()
    total_loss = 0
    for data, labels in train_loader:
        data = data.to(DEVICE)
        labels = labels.to(DEVICE)
        optimizer.zero_grad()
        outputs = model(data)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    avg_loss = total_loss / len(train_loader)
    print(f'Training Loss: {avg_loss:.4f}')

def infer(model, file_path):
    model.eval()
    features = preprocess_audio(file_path, sampling_rate=SAMPLING_RATE, n_mfcc=N_MFCC, seq_length=SEQ_LENGTH)
    features = torch.tensor(features, dtype=torch.float32).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        outputs = model(features)
        preds = outputs.argmax(dim=1)
        probabilities = torch.softmax(outputs, dim=1)
    classes = ['A', 'B']
    pred = classes[preds.item()]
    print(f'Prediction: {pred}')
    return pred, probabilities[:, 1].item()

def evaluate(model, val_loader, criterion):
    model.eval()
    total_loss = 0
    correct = 0
    with torch.no_grad():
        for data, labels in val_loader:
            data = data.to(DEVICE)
            labels = labels.to(DEVICE)
            outputs = model(data)
            loss = criterion(outputs, labels)
            total_loss += loss.item()
            preds = outputs.argmax(dim=1)
            correct += (preds == labels).sum().item()
    avg_loss = total_loss / len(val_loader)
    accuracy = correct / len(val_loader.dataset)
    print(f'Validation Loss: {avg_loss:.4f}')
    print(f'Accuracy: {accuracy:.4f}')
    return avg_loss

def main(mode, file=None):
    model = AudioClassifier().to(DEVICE)
    criterion = nn.NLLLoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    last_loss = None
    if mode == 'train':
        EPOCHS = int(input("Epochs: "))
        train_dataset = AudioDataset(TRAIN_DIR, seq_length=SEQ_LENGTH, sampling_rate=SAMPLING_RATE, n_mfcc=N_MFCC)
        val_dataset = AudioDataset(VAL_DIR, seq_length=SEQ_LENGTH, sampling_rate=SAMPLING_RATE, n_mfcc=N_MFCC)
        train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False)
        for epoch in range(EPOCHS):
            print(f'Epoch {epoch+1}/{EPOCHS}')
            train(model, train_loader, criterion, optimizer)
            loss = evaluate(model, val_loader, criterion)
            if last_loss is not None:
                delta = loss - last_loss
                print(f"Validation Loss delta: {delta * -100:.2f}%")
            last_loss = loss
            print('-' * 3)
        filename = f'lstm_model_{SAMPLING_RATE}_{N_MFCC}_{HIDDEN_SIZE}_{NUM_LAYERS}_{SEQ_LENGTH}_{EPOCHS}.pth'
        torch.save(model.state_dict(), filename)
        print('Model saved as', filename)
        print('Model saved')
    elif mode == 'infer':
        if file is None:
            raise ValueError("File path is required for inference mode.")
        if not os.path.exists(file):
            print(f'File "{file}" does not exist.')
            return
        expected_filename = f'lstm_model_{SAMPLING_RATE}_{N_MFCC}_{HIDDEN_SIZE}_{NUM_LAYERS}_{SEQ_LENGTH}_*.pth'
        matching_files = glob.glob(expected_filename)
        if not matching_files:
            raise ValueError("No matching model file found for the current architecture parameters.")
        filename = matching_files[0]
        checkpoint = torch.load(filename, map_location=DEVICE, weights_only=True)
        print(f'Loaded model from {filename}')
        model.load_state_dict(checkpoint)
        pred_class, prob_B = infer(model, file)
        print(f'{prob_B}')
        return pred_class, prob_B

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Audio Classification Script')
    parser.add_argument('--mode', type=str, required=True, choices=['train', 'infer'], help='Mode: train or infer')
    parser.add_argument('--file', type=str, help='Path to audio file for inference (required for infer mode)')
    args = parser.parse_args()
    main(args.mode, args.file)

