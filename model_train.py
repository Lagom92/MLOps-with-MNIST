import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torchinfo import summary
from sklearn.datasets import fetch_openml
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

import mlflow


class CNNModel(nn.Module):
    def __init__(self):
        super(CNNModel, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.fc1 = nn.Linear(64 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(-1, 64 * 7 * 7)  # Flatten the tensor
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)

def train(model, device, loss_fn, train_loader, optimizer, epoch):
    model.train()
    correct = 0
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = loss_fn(output, target)
        loss.backward()
        optimizer.step()
        
        pred = output.argmax(dim=1, keepdim=True)
        correct += pred.eq(target.view_as(pred)).sum().item()
        train_acc = correct / len(train_loader.dataset)
        
        if batch_idx % 100 == 0:
            step = batch_idx // 100 * (epoch+1) 
            mlflow.log_metric('loss', f'{loss:.4f}', step=step)
            mlflow.log_metric('accuracy', f'{train_acc:.4f}', step=step)
            print(f'Train Epoch: {epoch} [{batch_idx * len(data)}/{len(train_loader.dataset)}'
                  f' ({100. * batch_idx / len(train_loader):.0f}%)]\tLoss: {loss.item():.6f}')

def test(model, device, loss_fn, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += loss_fn(output, target).item()  # 배치 손실 더하기
            pred = output.argmax(dim=1, keepdim=True)  # 가장 높은 log-probability를 가진 인덱스 찾기
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)
    test_acc = correct / len(test_loader.dataset)
    mlflow.log_metric('test_loss', f'{test_loss:.4f}')
    mlflow.log_metric('test_accuracy', f'{test_acc:.4f}')
    
    print(f'\nTest set: Average loss: {test_loss:.4f}, Accuracy: {correct}/{len(test_loader.dataset)}'
          f' ({100. * correct / len(test_loader.dataset):.0f}%)\n')


# mlflow.set_tracking_uri(uri="http://127.0.0.1:5000")/
mlflow.set_experiment("model-train")
def main():    
    # MNIST 데이터셋 로드
    mnist = fetch_openml('mnist_784', version=1)
    X, y = mnist["data"], mnist["target"].astype(int)

    # 데이터를 학습용과 테스트용으로 나누기
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=1/7, random_state=42)

    # 스케일링 (0~1 범위로)
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    
    # y_train과 y_test를 numpy 배열로 변환
    y_train = y_train.to_numpy()
    y_test = y_test.to_numpy()
    
    # PyTorch 텐서로 변환
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32).view(-1, 1, 28, 28)
    y_train_tensor = torch.tensor(y_train, dtype=torch.long)
    X_test_tensor = torch.tensor(X_test, dtype=torch.float32).view(-1, 1, 28, 28)
    y_test_tensor = torch.tensor(y_test, dtype=torch.long)

    # DataLoader 생성
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    test_dataset = TensorDataset(X_test_tensor, y_test_tensor)

    train_loader = DataLoader(dataset=train_dataset, batch_size=64, shuffle=True)
    test_loader = DataLoader(dataset=test_dataset, batch_size=1000, shuffle=False)

    # 모델 설정
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    
    epochs = 10
    loss_fn = nn.CrossEntropyLoss()
    model = CNNModel().to(device)
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    with mlflow.start_run() as run:
        params = {
            'epochs': epochs,
            'learning_rate': 1e-3,
            'train: batch_size': 64,
            'test: batch_size': 1000,
            'loss_function': loss_fn.__class__.__name__,
            'metric_function': 'Accuracy',
            'optimizer': 'Adam'
        }
        # Log Training Parameters
        mlflow.log_params(params)
        
        # Log model summary
        with open('model_summary.txt', 'w') as f:
            f.write(str(summary(model)))
        mlflow.log_artifact('model_summary.txt')
        
        # 모델 학습 및 평가
        for epoch in range(1, epochs+1):  # 10 에포크 동안 학습
            train(model, device, loss_fn, train_loader, optimizer, epoch)
            test(model, device, loss_fn, test_loader)

        test(model, device, loss_fn, test_loader)
    
if __name__ == "__main__":
    main()